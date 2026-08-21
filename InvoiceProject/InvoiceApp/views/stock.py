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
    agent_stocks = AgentStock.objects.filter(agent__company=user).select_related('agent', 'product').filter(quantity__gt=0).order_by('agent__name', 'product__name')
    loads = StockLoad.objects.filter(company=user).select_related('agent').prefetch_related('items__product').order_by('-date')[:30]
    returns = StockReturn.objects.filter(company=user).select_related('agent').prefetch_related('items__product').order_by('-date')[:30]

    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'agents': agents,
        'products': products,
        'agent_stocks': agent_stocks,
        'loads': loads,
        'returns': returns,
    }
    return render(request, 'stock_loads.html', context)


@require_http_methods(["POST"])
@login_required
def add_stock_load(request):
    user = request.user
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

    # Validation du stock MAGASIN avant toute écriture (on ne peut pas charger plus que ce qu'il y a)
    stock_preview = {}
    for product, quantity, unit_price in items:
        available = stock_preview.get(product.id, product.stock_quantity)
        if available < quantity:
            return JsonResponse({
                "success": False,
                "error": f"Stock magasin insuffisant pour {product.name} (disponible : {available})"
            }, status=400)
        stock_preview[product.id] = available - quantity

    with transaction.atomic():
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

    return JsonResponse({"success": True, "message": f"Chargement enregistré pour {agent.name}"})


@require_http_methods(["POST"])
@login_required
def add_stock_return(request):
    user = request.user
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

    # Validation du stock VENDEUR avant toute écriture (on ne peut pas retourner plus que ce qu'il a)
    stock_preview = {}
    for agent_stock, quantity in items:
        available = stock_preview.get(agent_stock.product_id, agent_stock.quantity)
        if available < quantity:
            return JsonResponse({
                "success": False,
                "error": f"{agent.name} n'a que {available} de {agent_stock.product.name} — impossible de retourner {quantity}"
            }, status=400)
        stock_preview[agent_stock.product_id] = available - quantity

    with transaction.atomic():
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

    return JsonResponse({"success": True, "message": f"Retour enregistré pour {agent.name}"})
