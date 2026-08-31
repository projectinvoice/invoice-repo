"""
Gestion des ventes.
"""
from ._common import *  # noqa: F401,F403


@require_http_methods(["GET"])
@login_required
def list_sales(request):
    user = request.user
    sales = user.sales.all()
    clients = user.clients.all()
    products = user.products.all()
    agents = user.agents.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'sales': sales,
        'clients': clients,
        'products': products,
        'agents': agents,
    }
    return render(request, 'sale_list.html', context)


@require_http_methods(["POST"])
@login_required 
def add_sale(request):
    sale_id = request.POST.get("sale_id")
    client_id = request.POST.get("client_id")
    agent_id = request.POST.get("agent_id")
    sale_items_payload = request.POST.get("sale_items")
    payment_type = request.POST.get("payment_type", "full")  # full | credit | partial
    amount_paid_input = request.POST.get("amount_paid", "")
    due_date_input = request.POST.get("due_date", "")

    if payment_type not in ("full", "credit", "partial"):
        payment_type = "full"

    if not client_id:
        return JsonResponse({"success": False, "error": "client_id requis"}, status=400)

    client = Client.objects.filter(id=client_id, company=request.user).first()
    if not client:
        return JsonResponse({"success": False, "error": "Client introuvable"}, status=404)

    agent = None
    if agent_id:
        agent = Agent.objects.filter(id=agent_id, company=request.user).first()
        if not agent:
            return JsonResponse({"success": False, "error": "Agent introuvable"}, status=404)

    if not sale_items_payload:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    try:
        parsed_items = json.loads(sale_items_payload)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Format des produits invalide"}, status=400)

    if not isinstance(parsed_items, list) or not parsed_items:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    items = []
    for item_data in parsed_items:
        product_id = item_data.get('product_id')
        quantity = item_data.get('quantity')
        unit_price = item_data.get('unit_price')
        if not product_id or not quantity:
            return JsonResponse({"success": False, "error": "Chaque ligne doit contenir un produit et une quantité"}, status=400)

        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "quantity doit être un nombre"}, status=400)

        product = Product.objects.filter(id=product_id, company=request.user).first()
        if not product:
            return JsonResponse({"success": False, "error": "Produit introuvable"}, status=404)

        if unit_price in [None, '', 'null']:
            unit_price = product.price
        else:
            try:
                unit_price = Decimal(str(unit_price))
            except (ValueError, TypeError, InvalidOperation):
                return JsonResponse({"success": False, "error": "unit_price doit être un nombre"}, status=400)

        # La devise suit toujours le produit : pas de choix manuel de devise
        items.append((product, quantity, unit_price, product.currency))

    # Récupère la vente existante (édition) sans encore rien modifier
    sale = None
    old_items = []
    if sale_id:
        sale = Sale.objects.filter(id=sale_id, company=request.user).first()
        if not sale:
            return JsonResponse({"success": False, "error": "Vente introuvable"}, status=404)
        old_items = list(sale.sale_items.select_related('product').all())

    is_new_sale = sale is None

    # Simule le stock disponible (en remettant virtuellement les anciennes quantités
    # si on édite) AVANT de valider — aucune écriture en base à ce stade
    stock_preview = {}
    for old_item in old_items:
        base = stock_preview.get(old_item.product_id, old_item.product.stock_quantity)
        stock_preview[old_item.product_id] = base + old_item.quantity

    for product, quantity, unit_price, item_currency in items:
        available = stock_preview.get(product.id, product.stock_quantity)
        if available < quantity:
            return JsonResponse({
                "success": False,
                "error": f"Stock insuffisant pour {product.name} (disponible : {available})"
            }, status=400)
        stock_preview[product.id] = available - quantity

    # Paiement (comptant / crédit / avance) — uniquement à la création d'une vente.
    # La modification du paiement d'une vente existante se fait depuis l'espace Factures.
    amount_paid = None
    due_date = None
    if is_new_sale:
        sale_total = sum((unit_price * quantity for _, quantity, unit_price, _ in items), Decimal('0.00'))
        today = timezone.now().date()
        if payment_type == "full":
            amount_paid = sale_total
            due_date = today
        elif payment_type == "credit":
            amount_paid = Decimal('0.00')
            if not due_date_input:
                return JsonResponse({"success": False, "error": "Indique une date d'échéance pour le crédit"}, status=400)
            try:
                due_date = timezone.datetime.strptime(due_date_input, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"success": False, "error": "Date d'échéance invalide"}, status=400)
        else:  # partial
            if not amount_paid_input:
                return JsonResponse({"success": False, "error": "Indique le montant déjà versé"}, status=400)
            try:
                amount_paid = Decimal(str(amount_paid_input))
            except (InvalidOperation, ValueError):
                return JsonResponse({"success": False, "error": "Montant versé invalide"}, status=400)
            if amount_paid <= 0 or amount_paid >= sale_total:
                return JsonResponse({"success": False, "error": "Le montant versé doit être supérieur à 0 et inférieur au total (sinon utilise « payé en totalité »)"}, status=400)
            if not due_date_input:
                return JsonResponse({"success": False, "error": "Indique une date d'échéance pour le solde restant"}, status=400)
            try:
                due_date = timezone.datetime.strptime(due_date_input, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"success": False, "error": "Date d'échéance invalide"}, status=400)

    # Tout est validé : on applique les changements, tout ou rien
    with transaction.atomic():
        if sale:
            for old_item in old_items:
                old_item.product.stock_quantity += old_item.quantity
                old_item.product.save(update_fields=['stock_quantity'])
            sale.client = client
            sale.agent = agent
            sale.sale_items.all().delete()
        else:
            sale = Sale.objects.create(company=request.user, client=client, agent=agent)

        for product, quantity, unit_price, item_currency in items:
            product.refresh_from_db(fields=['stock_quantity'])
            product.stock_quantity -= quantity
            product.save(update_fields=['stock_quantity'])

            SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                currency=item_currency,
            )

        sale.save()

        invoice = None
        if is_new_sale:
            # Facture générée automatiquement, une seule fois, numéro garanti unique et séquentiel
            # (même logique que côté espace vendeur, pour un comportement cohérent).
            invoice_number = generate_invoice_number(request.user)
            invoice = Invoice.objects.create(
                company=request.user,
                sale=sale,
                invoice_number=invoice_number,
                due_date=due_date,
                amount_paid=amount_paid,
            )
            invoice.refresh_status()
            invoice.save(update_fields=['status'])

            if amount_paid > 0:
                Payment.objects.create(
                    invoice=invoice, amount=amount_paid,
                    note="Versement à la vente" if payment_type == "partial" else "Paiement comptant"
                )

    response = {"success": True, "sale_id": sale.id, "message": "Vente enregistrée"}
    if invoice:
        response["invoice_id"] = invoice.id
        response["invoice_number"] = invoice.invoice_number
    return JsonResponse(response)


@require_http_methods(["POST"])
@login_required
def delete_sale(request):
    sale_id = request.POST.get("sale_id")
    if not sale_id:
        return JsonResponse({"success": False, "error": "sale_id requis"}, status=400)

    sale = Sale.objects.filter(id=sale_id, company=request.user).first()
    if not sale:
        return JsonResponse({"success": False, "error": "Vente introuvable"}, status=404)

    with transaction.atomic():
        # Recrédite le stock de chaque produit avant de supprimer la vente,
        # sinon les quantités vendues restent définitivement déduites du stock.
        for item in sale.sale_items.select_related('product').all():
            item.product.refresh_from_db(fields=['stock_quantity'])
            item.product.stock_quantity += item.quantity
            item.product.save(update_fields=['stock_quantity'])
        sale.delete()

    return JsonResponse({"success": True, "message": "Vente supprimée"})
