"""
Gestion des factures, paiements de facture et generation de PDF.
"""
from ._common import *  # noqa: F401,F403


@require_http_methods(["GET"])
@login_required
def list_invoices(request):
    user = request.user
    invoices = user.invoices.all()
    sales = user.sales.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'invoices': invoices,
        'sales': sales,
    }
    return render(request, 'invoice_list.html', context)


@require_http_methods(["POST"])
@login_required
def add_invoice(request):
    invoice_id = request.POST.get("invoice_id")
    sale_id = request.POST.get("sale_id")
    invoice_number = request.POST.get("invoice_number")
    due_date = request.POST.get("due_date")
    status = request.POST.get("status", "pending")
    if not sale_id or not invoice_number or not due_date:
        return JsonResponse({"success": False, "error": "sale_id, invoice_number et due_date requis"}, status=400)
    
    sale = Sale.objects.filter(id=sale_id, company=request.user).first()
    if not sale:
        return JsonResponse({"success": False, "error": "Vente introuvable"}, status=404)
    
    if invoice_id:
        invoice = Invoice.objects.filter(id=invoice_id, company=request.user).first()
        if not invoice:
            return JsonResponse({"success": False, "error": "Facture introuvable"}, status=404)
        invoice.sale = sale
        invoice.invoice_number = invoice_number
        invoice.due_date = due_date
        invoice.status = status
        invoice.save()
    else:
        invoice = Invoice.objects.create(
            company=request.user,
            sale=sale,
            invoice_number=invoice_number,
            due_date=due_date,
            status=status,
        )
    return JsonResponse({"success": True, "invoice_id": invoice.id, "message": "Facture enregistrée"})


@require_http_methods(["POST"])
@login_required
def delete_invoice(request):
    invoice_id = request.POST.get("invoice_id")
    if not invoice_id:
        return JsonResponse({"success": False, "error": "invoice_id requis"}, status=400)
    Invoice.objects.filter(id=invoice_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Facture supprimée"})


@require_http_methods(["POST"])
@login_required
def record_invoice_payment(request):
    """Enregistre un paiement supplémentaire sur une facture à crédit ou partiellement payée."""
    invoice_id = request.POST.get("invoice_id")
    amount_input = request.POST.get("amount")

    invoice = Invoice.objects.filter(id=invoice_id, company=request.user).select_related('sale').first()
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

    note = request.POST.get("note", "")

    with transaction.atomic():
        Payment.objects.create(invoice=invoice, amount=amount, note=note)
        invoice.amount_paid += amount
        invoice.refresh_status()
        invoice.save(update_fields=['amount_paid', 'status'])

    return JsonResponse({
        "success": True,
        "message": "Paiement enregistré",
        "status": invoice.status,
        "amount_paid": str(invoice.amount_paid),
        "balance_due": str(invoice.balance_due),
    })


def _build_invoice_pdf_bytes(invoice):
    """Génère le PDF de la facture et retourne ses octets bruts (réutilisable pour
    le téléchargement HTTP ou tout autre usage futur)."""
    company = invoice.company
    sale = invoice.sale
    client = sale.client
    items = sale.sale_items.select_related('product').all()

    buffer = BytesIO()
    p = pdf_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    INDIGO = colors.HexColor('#6366F1')
    DARK = colors.HexColor('#1A2238')
    GREY = colors.HexColor('#64748B')

    # ── EN-TÊTE : logo + entreprise ──
    top = height - 20 * mm
    logo_drawn = False
    if company.logo and hasattr(company.logo, 'path'):
        try:
            p.drawImage(company.logo.path, 20 * mm, top - 18 * mm, width=22 * mm, height=22 * mm,
                        preserveAspectRatio=True, mask='auto')
            logo_drawn = True
        except Exception:
            logo_drawn = False

    text_x = 46 * mm if logo_drawn else 20 * mm
    p.setFillColor(DARK)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(text_x, top - 4 * mm, company.company_name)
    p.setFillColor(GREY)
    p.setFont("Helvetica", 9)
    if company.address:
        p.drawString(text_x, top - 10 * mm, company.address[:60])
    if company.phone or company.company_email:
        p.drawString(text_x, top - 15 * mm, f"{company.phone}  {company.company_email or ''}".strip())

    p.setFillColor(INDIGO)
    p.setFont("Helvetica-Bold", 22)
    p.drawRightString(width - 20 * mm, top - 4 * mm, "FACTURE")
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 11)
    p.drawRightString(width - 20 * mm, top - 12 * mm, invoice.invoice_number)
    p.setFont("Helvetica", 9)
    p.setFillColor(GREY)
    p.drawRightString(width - 20 * mm, top - 17 * mm, f"Émise le {invoice.issued_date.strftime('%d/%m/%Y')}")
    p.drawRightString(width - 20 * mm, top - 22 * mm, f"Échéance : {invoice.due_date.strftime('%d/%m/%Y')}")

    status_labels = dict(Invoice._meta.get_field('status').choices)
    status_colors = {
        'paid': colors.HexColor('#10B981'),
        'pending': colors.HexColor('#F59E0B'),
        'partial': colors.HexColor('#38BDF8'),
        'overdue': colors.HexColor('#F43F5E'),
    }
    p.setFillColor(status_colors.get(invoice.status, colors.grey))
    p.setFont("Helvetica-Bold", 9)
    p.drawRightString(width - 20 * mm, top - 28 * mm, status_labels.get(invoice.status, invoice.status).upper())

    p.setStrokeColor(colors.HexColor('#E2E8F0'))
    p.line(20 * mm, top - 34 * mm, width - 20 * mm, top - 34 * mm)

    # ── BLOC CLIENT ──
    client_top = top - 44 * mm
    p.setFillColor(GREY)
    p.setFont("Helvetica-Bold", 9)
    p.drawString(20 * mm, client_top, "FACTURÉ À")
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 12)
    display_name = client.shop_name or client.name
    p.drawString(20 * mm, client_top - 7 * mm, display_name)
    p.setFont("Helvetica", 9.5)
    p.setFillColor(GREY)
    line_y = client_top - 13 * mm
    if client.shop_name:
        p.drawString(20 * mm, line_y, f"Contact : {client.name}")
        line_y -= 5 * mm
    if client.phone:
        p.drawString(20 * mm, line_y, client.phone)
        line_y -= 5 * mm
    if client.address:
        p.drawString(20 * mm, line_y, client.address[:70])

    agent_name = sale.agent.name if sale.agent else None
    if agent_name:
        p.setFillColor(GREY)
        p.setFont("Helvetica", 9)
        p.drawRightString(width - 20 * mm, client_top, f"Vendeur : {agent_name}")

    # ── TABLEAU DES PRODUITS ──
    table_top = client_top - 30 * mm
    p.setFillColor(DARK)
    p.rect(20 * mm, table_top - 7 * mm, width - 40 * mm, 7 * mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 9)
    p.drawString(23 * mm, table_top - 5 * mm, "Produit")
    p.drawCentredString(125 * mm, table_top - 5 * mm, "Qté")
    p.drawRightString(160 * mm, table_top - 5 * mm, "Prix unitaire")
    p.drawRightString(width - 23 * mm, table_top - 5 * mm, "Total")

    row_y = table_top - 15 * mm
    p.setFont("Helvetica", 9.5)
    for i, item in enumerate(items):
        if row_y < 30 * mm:
            p.showPage()
            row_y = height - 20 * mm
        bg = colors.HexColor('#F8FAFC') if i % 2 == 0 else colors.white
        p.setFillColor(bg)
        p.rect(20 * mm, row_y - 4 * mm, width - 40 * mm, 8 * mm, fill=1, stroke=0)
        p.setFillColor(colors.black)
        p.drawString(23 * mm, row_y, item.product.name[:48])
        p.drawCentredString(125 * mm, row_y, str(item.quantity))
        symbols = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}
        symbol = symbols.get(item.currency, item.currency)
        p.drawRightString(160 * mm, row_y, f"{item.unit_price:,.2f} {symbol}")
        p.drawRightString(width - 23 * mm, row_y, f"{item.total_price:,.2f} {symbol}")
        row_y -= 8 * mm

    row_y -= 4 * mm
    p.setStrokeColor(colors.HexColor('#E2E8F0'))
    p.line(120 * mm, row_y, width - 20 * mm, row_y)
    row_y -= 9 * mm
    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(INDIGO)
    p.drawRightString(width - 23 * mm, row_y, f"Total : {sale.formatted_total_price}")

    if invoice.status != 'paid':
        row_y -= 7 * mm
        p.setFont("Helvetica", 9.5)
        p.setFillColor(colors.HexColor('#10B981'))
        p.drawRightString(width - 23 * mm, row_y, f"Déjà payé : {invoice.formatted_amount_paid}")
        row_y -= 6 * mm
        p.setFillColor(colors.HexColor('#F43F5E'))
        p.setFont("Helvetica-Bold", 10.5)
        p.drawRightString(width - 23 * mm, row_y, f"Reste à payer : {invoice.formatted_balance_due}")

    p.setFillColor(GREY)
    p.setFont("Helvetica-Oblique", 8)
    p.drawCentredString(width / 2, 15 * mm, "Merci de votre confiance.")
    p.setFont("Helvetica", 7)
    p.drawCentredString(width / 2, 10 * mm, f"{company.company_name} — Facture générée automatiquement, numéro unique {invoice.invoice_number}")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.getvalue()


def _render_invoice_pdf(invoice):
    """Réponse HTTP de téléchargement du PDF de la facture."""
    pdf_bytes = _build_invoice_pdf_bytes(invoice)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'
    return response


@require_http_methods(["GET"])
@login_required
def invoice_pdf(request, invoice_id):
    invoice = Invoice.objects.filter(id=invoice_id, company=request.user).select_related(
        'sale', 'sale__client', 'company'
    ).first()
    if not invoice:
        return HttpResponse("Facture introuvable", status=404)
    return _render_invoice_pdf(invoice)
