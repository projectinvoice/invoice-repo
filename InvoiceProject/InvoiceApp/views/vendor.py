"""
Espace vendeur (agents) : authentification separee par code entreprise + PIN.
"""
from ._common import *  # noqa: F401,F403
from .invoices import _render_invoice_pdf


def generate_invoice_number(company):
    """Génère un numéro de facture séquentiel et unique par entreprise, sans collision
    même en cas de ventes simultanées (verrouillage de la ligne de l'entreprise)."""
    with transaction.atomic():
        locked_company = User.objects.select_for_update().get(pk=company.pk)
        number = locked_company.next_invoice_number
        locked_company.next_invoice_number = number + 1
        locked_company.save(update_fields=['next_invoice_number'])
    year = timezone.now().year
    return f"FAC-{year}-{number:05d}"


def agent_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        agent_id = request.session.get('agent_id')
        if not agent_id:
            return redirect('vendor_login')
        agent = Agent.objects.filter(id=agent_id, is_active=True).select_related('company', 'role').first()
        if not agent:
            request.session.flush()
            return redirect('vendor_login')
        request.agent = agent
        return view_func(request, *args, **kwargs)
    return wrapper


@require_http_methods(["GET", "POST"])
def vendor_login(request):
    if request.method == "GET":
        return render(request, 'vendor_login.html')

    company_code = request.POST.get("company_code", "").strip().upper()
    pin = request.POST.get("pin", "").strip()

    if not company_code or not pin:
        return JsonResponse({"success": False, "error": "Code entreprise et PIN requis"}, status=400)

    company = User.objects.filter(agent_login_code=company_code).first()
    if not company:
        return JsonResponse({"success": False, "error": "Code entreprise invalide"}, status=400)

    matched_agent = None
    for agent in Agent.objects.filter(company=company, is_active=True):
        if agent.check_pin(pin):
            matched_agent = agent
            break

    if not matched_agent:
        return JsonResponse({"success": False, "error": "PIN invalide"}, status=400)

    request.session['agent_id'] = matched_agent.id
    return JsonResponse({"success": True, "message": "Connecté", "redirect": "/vendeur/"})


@require_http_methods(["GET", "POST"])
def vendor_logout(request):
    request.session.flush()
    return redirect('vendor_login')


@require_http_methods(["GET"])
@agent_login_required
def vendor_invoice_pdf(request, invoice_id):
    invoice = Invoice.objects.filter(id=invoice_id, company=request.agent.company).select_related(
        'sale', 'sale__client', 'company'
    ).first()
    if not invoice:
        return HttpResponse("Facture introuvable", status=404)
    return _render_invoice_pdf(invoice)


@agent_login_required
def vendor_dashboard(request):
    agent = request.agent
    agent_stocks = AgentStock.objects.filter(agent=agent, quantity__gt=0).select_related('product').order_by('product__name')
    clients = Client.objects.filter(company=agent.company)
    recent_sales = Sale.objects.filter(company=agent.company, agent=agent).select_related('invoice', 'client').order_by('-date')[:15]
    context = {
        'agent': agent,
        'company_name': agent.company.company_name,
        'company_logo_url': agent.company.logo.url if agent.company.logo else None,
        'agent_stocks': agent_stocks,
        'clients': clients,
        'sales': recent_sales,
    }
    return render(request, 'vendor_dashboard.html', context)


@require_http_methods(["POST"])
@agent_login_required
def vendor_add_sale(request):
    agent = request.agent
    company = agent.company

    client_id = request.POST.get("client_id")
    new_client_name = request.POST.get("new_client_name", "").strip()
    new_client_shop_name = request.POST.get("new_client_shop_name", "").strip()
    new_client_phone = request.POST.get("new_client_phone", "").strip()
    sale_items_payload = request.POST.get("sale_items")
    payment_type = request.POST.get("payment_type", "full")  # full | credit | partial
    amount_paid_input = request.POST.get("amount_paid", "")
    due_date_input = request.POST.get("due_date", "")

    if payment_type not in ("full", "credit", "partial"):
        payment_type = "full"

    # Client existant OU création rapide d'un nouveau client
    if client_id:
        client = Client.objects.filter(id=client_id, company=company).first()
        if not client:
            return JsonResponse({"success": False, "error": "Client introuvable"}, status=404)
    elif new_client_name:
        client = Client.objects.create(company=company, name=new_client_name, shop_name=new_client_shop_name, phone=new_client_phone)
    else:
        return JsonResponse({"success": False, "error": "Sélectionnez un client ou renseignez son nom"}, status=400)

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
        if not product_id or not quantity:
            return JsonResponse({"success": False, "error": "Chaque ligne doit contenir un produit et une quantité"}, status=400)
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "quantity doit être un nombre"}, status=400)

        # Sécurité : le prix vient TOUJOURS du stock personnel du vendeur (fixé par la secrétaire
        # au moment du chargement), jamais de ce que le vendeur envoie, et jamais du prix catalogue.
        agent_stock = AgentStock.objects.filter(agent=agent, product_id=product_id).select_related('product').first()
        if not agent_stock:
            return JsonResponse({"success": False, "error": "Ce produit n'est pas dans ton stock"}, status=404)

        items.append((agent_stock, quantity))

    # Validation du stock PERSONNEL du vendeur avant toute écriture
    stock_preview = {}
    for agent_stock, quantity in items:
        available = stock_preview.get(agent_stock.product_id, agent_stock.quantity)
        if available < quantity:
            return JsonResponse({
                "success": False,
                "error": f"Stock insuffisant pour {agent_stock.product.name} (disponible chez toi : {available})"
            }, status=400)
        stock_preview[agent_stock.product_id] = available - quantity

    sale_total = sum((agent_stock.unit_price * quantity for agent_stock, quantity in items), Decimal('0.00'))

    # Validation du paiement (comptant / crédit / avance) avant toute écriture
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

    with transaction.atomic():
        sale = Sale.objects.create(company=company, client=client, agent=agent)

        for agent_stock, quantity in items:
            agent_stock.refresh_from_db(fields=['quantity'])
            agent_stock.quantity -= quantity
            agent_stock.save(update_fields=['quantity'])

            SaleItem.objects.create(
                sale=sale,
                product=agent_stock.product,
                quantity=quantity,
                unit_price=agent_stock.unit_price,
                currency=agent_stock.currency,
            )

        sale.save()

        # Facture générée automatiquement, une seule fois, numéro garanti unique et séquentiel
        invoice_number = generate_invoice_number(company)
        invoice = Invoice.objects.create(
            company=company,
            sale=sale,
            invoice_number=invoice_number,
            due_date=due_date,
            amount_paid=amount_paid,
        )
        invoice.refresh_status()
        invoice.save(update_fields=['status'])

        if amount_paid > 0:
            Payment.objects.create(
                invoice=invoice, amount=amount_paid, recorded_by_agent=agent,
                note="Versement à la vente" if payment_type == "partial" else "Paiement comptant"
            )

    return JsonResponse({
        "success": True,
        "message": "Vente enregistrée",
        "sale_id": sale.id,
        "invoice_number": invoice.invoice_number,
        "invoice_id": invoice.id,
    }) 


@require_http_methods(["POST"])
@agent_login_required
def vendor_add_payment(request):
    """Le vendeur enregistre un versement complémentaire sur une vente à crédit/avance qu'il a faite."""
    agent = request.agent
    invoice_id = request.POST.get("invoice_id")
    amount_input = request.POST.get("amount")

    invoice = Invoice.objects.filter(id=invoice_id, company=agent.company, sale__agent=agent).select_related('sale').first()
    if not invoice:
        return JsonResponse({"success": False, "error": "Facture introuvable"}, status=404)

    if not amount_input:
        return JsonResponse({"success": False, "error": "Montant requis"}, status=400)
    try:
        amount = Decimal(str(amount_input))
    except (InvalidOperation, ValueError):
        return JsonResponse({"success": False, "error": "Montant invalide"}, status=400)

    if amount <= 0:
        return JsonResponse({"success": False, "error": "Le montant doit être supérieur à 0"}, status=400)
    if amount > invoice.balance_due:
        return JsonResponse({
            "success": False,
            "error": f"Le montant dépasse le solde restant ({invoice.formatted_balance_due})"
        }, status=400)

    with transaction.atomic():
        Payment.objects.create(invoice=invoice, amount=amount, recorded_by_agent=agent, note="Versement enregistré par le vendeur")
        invoice.amount_paid += amount
        invoice.refresh_status()
        invoice.save(update_fields=['amount_paid', 'status'])

    return JsonResponse({
        "success": True,
        "message": "Paiement enregistré",
        "status": invoice.status,
        "balance_due": str(invoice.balance_due),
    })
