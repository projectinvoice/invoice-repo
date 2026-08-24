"""
Chargements et retours de stock vendeur, geres par l'entreprise.
"""
from ._common import *  # noqa: F401,F403


@require_http_methods(["GET"])
@login_required
def list_stock_loads(request):
    user = request.user
    agents = user.agents.all()
    products = user.products.all()
    engines = user.engines.all()
    agent_stocks = AgentStock.objects.filter(agent__company=user).select_related('agent', 'product').filter(quantity__gt=0).order_by('agent__name', 'product__name')
    loads = StockLoad.objects.filter(company=user).select_related('agent').prefetch_related('items__product').order_by('-date')[:30]
    returns = StockReturn.objects.filter(company=user).select_related('agent').prefetch_related('items__product').order_by('-date')[:30]

    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'agents': agents,
        'products': products,
        'engines': engines,
        'agent_stocks': agent_stocks,
        'loads': loads,
        'returns': returns,
    }
    return render(request, 'stock_loads.html', context)


@require_http_methods(["POST"])
@login_required
def add_stock_load(request):
    user = request.user
    load_id = request.POST.get("load_id")
    agent_id = request.POST.get("agent_id")
    note = request.POST.get("note", "")
    items_payload = request.POST.get("items")

    agent = Agent.objects.filter(id=agent_id, company=user).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent introuvable"}, status=404)

    if not items_payload:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)
    try:
        parsed_items = json.loads(items_payload)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Format des produits invalide"}, status=400)
    if not isinstance(parsed_items, list) or not parsed_items:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    items = []
    for item_data in parsed_items:
        product_id = item_data.get('product_id')
        quantity = item_data.get('quantity')
        unit_price = item_data.get('unit_price')
        if not product_id or not quantity or unit_price in [None, '']:
            return JsonResponse({"success": False, "error": "Chaque ligne doit contenir un produit, une quantité et un prix"}, status=400)
        try:
            quantity = int(quantity)
            unit_price = Decimal(str(unit_price))
        except (ValueError, TypeError, InvalidOperation):
            return JsonResponse({"success": False, "error": "quantity et unit_price doivent être des nombres"}, status=400)

        product = Product.objects.filter(id=product_id, company=user).first()
        if not product:
            return JsonResponse({"success": False, "error": "Produit introuvable"}, status=404)

        items.append((product, quantity, unit_price))

    # Récupère le chargement existant (édition) sans encore rien modifier
    load = None
    old_items = []
    if load_id:
        load = StockLoad.objects.filter(id=load_id, company=user).first()
        if not load:
            return JsonResponse({"success": False, "error": "Chargement introuvable"}, status=404)
        old_items = list(load.items.select_related('product').all())

        # Si on édite, il faut d'abord vérifier qu'on peut bien "annuler" les anciennes lignes :
        # le vendeur doit encore avoir au moins ces quantités dans son stock personnel
        # (sinon il a déjà vendu ou retourné une partie, impossible d'éditer sans casser les comptes).
        for old_item in old_items:
            agent_stock = AgentStock.objects.filter(agent=load.agent, product=old_item.product).first()
            available = agent_stock.quantity if agent_stock else 0
            if available < old_item.quantity:
                return JsonResponse({
                    "success": False,
                    "error": f"Impossible de modifier : {load.agent.name} a déjà utilisé une partie du stock de {old_item.product.name} chargé initialement"
                }, status=400)

    # Validation du stock MAGASIN avant toute écriture (on ne peut pas charger plus que ce qu'il y a).
    # En édition, on remet virtuellement les anciennes quantités en stock magasin avant de comparer.
    stock_preview = {}
    for old_item in old_items:
        base = stock_preview.get(old_item.product_id, old_item.product.stock_quantity)
        stock_preview[old_item.product_id] = base + old_item.quantity

    for product, quantity, unit_price in items:
        available = stock_preview.get(product.id, product.stock_quantity)
        if available < quantity:
            return JsonResponse({
                "success": False,
                "error": f"Stock magasin insuffisant pour {product.name} (disponible : {available})"
            }, status=400)
        stock_preview[product.id] = available - quantity

    with transaction.atomic():
        if load:
            # Annule l'effet des anciennes lignes (remet en stock magasin, retire du stock vendeur)
            for old_item in old_items:
                old_item.product.refresh_from_db(fields=['stock_quantity'])
                old_item.product.stock_quantity += old_item.quantity
                old_item.product.save(update_fields=['stock_quantity'])

                agent_stock = AgentStock.objects.filter(agent=load.agent, product=old_item.product).first()
                if agent_stock:
                    agent_stock.quantity -= old_item.quantity
                    agent_stock.save(update_fields=['quantity'])

            load.agent = agent
            load.note = note
            load.items.all().delete()
        else:
            load = StockLoad.objects.create(company=user, agent=agent, note=note)

        for product, quantity, unit_price in items:
            product.refresh_from_db(fields=['stock_quantity'])
            product.stock_quantity -= quantity
            product.save(update_fields=['stock_quantity'])

            StockLoadItem.objects.create(
                load=load, product=product, quantity=quantity,
                unit_price=unit_price, currency=product.currency,
            )

            agent_stock, _ = AgentStock.objects.get_or_create(
                agent=agent, product=product,
                defaults={'quantity': 0, 'unit_price': unit_price, 'currency': product.currency}
            )
            agent_stock.quantity += quantity
            agent_stock.unit_price = unit_price
            agent_stock.currency = product.currency
            agent_stock.save()

        load.save()

    message = "Chargement modifié" if load_id else f"Chargement enregistré pour {agent.name}"
    return JsonResponse({"success": True, "message": message, "load_id": load.id})


@require_http_methods(["POST"])
@login_required
def delete_stock_load(request):
    load_id = request.POST.get("load_id")
    if not load_id:
        return JsonResponse({"success": False, "error": "load_id requis"}, status=400)

    load = StockLoad.objects.filter(id=load_id, company=request.user).select_related('agent').first()
    if not load:
        return JsonResponse({"success": False, "error": "Chargement introuvable"}, status=404)

    items = list(load.items.select_related('product').all())

    # On ne peut annuler ce chargement que si le vendeur a encore toutes les quantités
    # correspondantes dans son stock personnel (sinon il en a déjà vendu ou retourné une partie).
    for item in items:
        agent_stock = AgentStock.objects.filter(agent=load.agent, product=item.product).first()
        available = agent_stock.quantity if agent_stock else 0
        if available < item.quantity:
            return JsonResponse({
                "success": False,
                "error": f"Impossible de supprimer : {load.agent.name} a déjà utilisé une partie du stock de {item.product.name} chargé"
            }, status=400)

    with transaction.atomic():
        for item in items:
            item.product.refresh_from_db(fields=['stock_quantity'])
            item.product.stock_quantity += item.quantity
            item.product.save(update_fields=['stock_quantity'])

            agent_stock = AgentStock.objects.filter(agent=load.agent, product=item.product).first()
            if agent_stock:
                agent_stock.quantity -= item.quantity
                agent_stock.save(update_fields=['quantity'])

        load.delete()  # cascade supprime les StockLoadItem associées

    return JsonResponse({"success": True, "message": "Chargement supprimé"})


@require_http_methods(["POST"])
@login_required
def add_stock_return(request):
    user = request.user
    return_id = request.POST.get("return_id")
    agent_id = request.POST.get("agent_id")
    note = request.POST.get("note", "")
    items_payload = request.POST.get("items")

    agent = Agent.objects.filter(id=agent_id, company=user).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent introuvable"}, status=404)

    if not items_payload:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)
    try:
        parsed_items = json.loads(items_payload)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Format des produits invalide"}, status=400)
    if not isinstance(parsed_items, list) or not parsed_items:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    # Récupère le retour existant (édition) sans encore rien modifier
    stock_return = None
    old_items = []
    if return_id:
        stock_return = StockReturn.objects.filter(id=return_id, company=user).first()
        if not stock_return:
            return JsonResponse({"success": False, "error": "Retour introuvable"}, status=404)
        old_items = list(stock_return.items.select_related('product').all())

        # Si on édite, il faut pouvoir "annuler" les anciennes lignes : le stock magasin
        # doit encore contenir au moins ces quantités (sinon déjà revendu/re-chargé ailleurs).
        for old_item in old_items:
            old_item.product.refresh_from_db(fields=['stock_quantity'])
            if old_item.product.stock_quantity < old_item.quantity:
                return JsonResponse({
                    "success": False,
                    "error": f"Impossible de modifier : le stock magasin de {old_item.product.name} a déjà été utilisé depuis ce retour"
                }, status=400)

    items = []
    for item_data in parsed_items:
        product_id = item_data.get('product_id')
        quantity = item_data.get('quantity')
        if not product_id or not quantity:
            return JsonResponse({"success": False, "error": "Chaque ligne doit contenir un produit et une quantité"}, status=400)
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "quantity doit être un nombre"}, status=400)

        agent_stock = AgentStock.objects.filter(agent=agent, product_id=product_id).select_related('product').first()
        if not agent_stock:
            return JsonResponse({"success": False, "error": "Ce vendeur n'a pas ce produit en stock"}, status=404)

        items.append((agent_stock, quantity))

    # Validation du stock VENDEUR avant toute écriture. En édition, on remet virtuellement
    # les anciennes quantités retournées dans le stock vendeur avant de comparer.
    stock_preview = {}
    if stock_return:
        for old_item in old_items:
            agent_stock_old = AgentStock.objects.filter(agent=stock_return.agent, product=old_item.product).first()
            base = agent_stock_old.quantity if agent_stock_old else 0
            stock_preview[old_item.product_id] = base - old_item.quantity

    for agent_stock, quantity in items:
        available = stock_preview.get(agent_stock.product_id, agent_stock.quantity)
        if available < quantity:
            return JsonResponse({
                "success": False,
                "error": f"{agent.name} n'a que {available} de {agent_stock.product.name} — impossible de retourner {quantity}"
            }, status=400)
        stock_preview[agent_stock.product_id] = available - quantity

    with transaction.atomic():
        if stock_return:
            # Annule l'effet des anciennes lignes (retire du stock magasin, remet au vendeur)
            for old_item in old_items:
                old_item.product.refresh_from_db(fields=['stock_quantity'])
                old_item.product.stock_quantity -= old_item.quantity
                old_item.product.save(update_fields=['stock_quantity'])

                old_agent_stock, _ = AgentStock.objects.get_or_create(
                    agent=stock_return.agent, product=old_item.product,
                    defaults={'quantity': 0, 'unit_price': old_item.product.price, 'currency': old_item.product.currency}
                )
                old_agent_stock.quantity += old_item.quantity
                old_agent_stock.save(update_fields=['quantity'])

            stock_return.agent = agent
            stock_return.note = note
            stock_return.items.all().delete()
        else:
            stock_return = StockReturn.objects.create(company=user, agent=agent, note=note)

        for agent_stock, quantity in items:
            agent_stock.refresh_from_db(fields=['quantity'])
            agent_stock.quantity -= quantity
            agent_stock.save(update_fields=['quantity'])

            StockReturnItem.objects.create(stock_return=stock_return, product=agent_stock.product, quantity=quantity)

            product = agent_stock.product
            product.refresh_from_db(fields=['stock_quantity'])
            product.stock_quantity += quantity
            product.save(update_fields=['stock_quantity'])

        stock_return.save()

    message = "Retour modifié" if return_id else f"Retour enregistré pour {agent.name}"
    return JsonResponse({"success": True, "message": message, "return_id": stock_return.id})


@require_http_methods(["POST"])
@login_required
def delete_stock_return(request):
    return_id = request.POST.get("return_id")
    if not return_id:
        return JsonResponse({"success": False, "error": "return_id requis"}, status=400)

    stock_return = StockReturn.objects.filter(id=return_id, company=request.user).select_related('agent').first()
    if not stock_return:
        return JsonResponse({"success": False, "error": "Retour introuvable"}, status=404)

    items = list(stock_return.items.select_related('product').all())

    # On ne peut annuler ce retour que si le stock magasin contient encore au moins
    # ces quantités (sinon elles ont déjà été revendues ou rechargées ailleurs).
    for item in items:
        item.product.refresh_from_db(fields=['stock_quantity'])
        if item.product.stock_quantity < item.quantity:
            return JsonResponse({
                "success": False,
                "error": f"Impossible de supprimer : le stock magasin de {item.product.name} a déjà été utilisé depuis ce retour"
            }, status=400)

    with transaction.atomic():
        for item in items:
            item.product.refresh_from_db(fields=['stock_quantity'])
            item.product.stock_quantity -= item.quantity
            item.product.save(update_fields=['stock_quantity'])

            agent_stock, _ = AgentStock.objects.get_or_create(
                agent=stock_return.agent, product=item.product,
                defaults={'quantity': 0, 'unit_price': item.product.price, 'currency': item.product.currency}
            )
            agent_stock.quantity += item.quantity
            agent_stock.save(update_fields=['quantity'])

        stock_return.delete()  # cascade supprime les StockReturnItem associées

    return JsonResponse({"success": True, "message": "Retour supprimé"})