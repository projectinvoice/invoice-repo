"""
Gestion des factures, paiements de facture et generation de PDF.
"""
from ._common import *  # noqa: F401,F403


@require_http_methods(["GET"])
@login_required
def list_invoices(request):
    user = request.user
    today = timezone.now().date()
    # Met à jour automatiquement les factures impayées dont l'échéance est dépassée
    user.invoices.filter(status__in=('pending', 'partial'), due_date__lt=today).update(status='overdue')
    invoices = user.invoices.select_related('sale', 'sale__client', 'sale__product').prefetch_related('sale__sale_items__product').all()
    sales = user.sales.select_related('client', 'product').prefetch_related('sale_items__product').all()
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
    invoice_number = (request.POST.get("invoice_number") or "").strip()
    due_date = request.POST.get("due_date")
    status = request.POST.get("status", "pending")
    if not sale_id or not invoice_number or not due_date:
        return JsonResponse({"success": False, "error": "sale_id, invoice_number et due_date requis"}, status=400)
    
    sale = Sale.objects.filter(id=sale_id, company=request.user).first()
    if not sale:
        return JsonResponse({"success": False, "error": "Vente introuvable"}, status=404)

    duplicate_num_qs = Invoice.objects.filter(company=request.user, invoice_number=invoice_number)
    duplicate_sale_qs = Invoice.objects.filter(company=request.user, sale=sale)
    if invoice_id:
        duplicate_num_qs = duplicate_num_qs.exclude(id=invoice_id)
        duplicate_sale_qs = duplicate_sale_qs.exclude(id=invoice_id)

    if duplicate_num_qs.exists():
        return JsonResponse({"success": False, "error": f"Le numéro de facture « {invoice_number} » existe déjà."}, status=400)
    if duplicate_sale_qs.exists():
        return JsonResponse({"success": False, "error": "Cette vente possède déjà une facture associée."}, status=400)

    if invoice_id:
        invoice = Invoice.objects.filter(id=invoice_id, company=request.user).first()
        if not invoice:
            return JsonResponse({"success": False, "error": "Facture introuvable"}, status=404)
        invoice.sale = sale
        invoice.invoice_number = invoice_number
        invoice.due_date = due_date
        invoice.status = status
        if status == 'paid' and invoice.amount_paid < sale.total_price:
            diff = sale.total_price - invoice.amount_paid
            invoice.amount_paid = sale.total_price
            Payment.objects.create(invoice=invoice, amount=diff, note="Règlement complet (statut Payée)")
        elif status == 'pending' and invoice.amount_paid >= sale.total_price:
            invoice.amount_paid = Decimal('0.00')
        invoice.save()
    else:
        initial_paid = sale.total_price if status == 'paid' else Decimal('0.00')
        invoice = Invoice.objects.create(
            company=request.user,
            sale=sale,
            invoice_number=invoice_number,
            due_date=due_date,
            amount_paid=initial_paid,
            status=status,
        )
        if initial_paid > 0:
            Payment.objects.create(invoice=invoice, amount=initial_paid, note="Paiement comptant")
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


def _format_currency_amount(amount, currency):
    symbols = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}
    sym = symbols.get(currency, currency)
    if currency == 'XOF':
        formatted = f"{amount:,.0f}".replace(',', ' ')
    else:
        formatted = f"{amount:,.2f}".replace(',', ' ')
    if currency == 'USD':
        return f"{sym}{formatted}"
    return f"{formatted} {sym}"


def _build_invoice_pdf_bytes(invoice):
    """Génère le document PDF officiel de la facture au format commercial A5 Portrait (148 x 210 mm)
    compact, moderne, élégant et parfaitement paginé."""
    company = invoice.company
    sale = invoice.sale
    client = sale.client
    raw_items = list(sale.sale_items.select_related('product').all())
    currency = sale.currency

    buffer = BytesIO()
    p = pdf_canvas.Canvas(buffer, pagesize=A5)
    width, height = A5  # 148 mm x 210 mm

    PRIMARY = colors.HexColor('#4F46E5')     # Indigo moderne
    DARK = colors.HexColor('#0F172A')        # Slate 900
    BODY = colors.HexColor('#334155')        # Slate 700
    MUTED = colors.HexColor('#64748B')       # Slate 500
    BORDER = colors.HexColor('#E2E8F0')      # Slate 200
    BG_LIGHT = colors.HexColor('#F8FAFC')    # Slate 50
    CARD_BG = colors.HexColor('#F1F5F9')     # Slate 100
    SUCCESS = colors.HexColor('#059669')     # Emerald
    WARNING = colors.HexColor('#D97706')     # Amber
    INFO = colors.HexColor('#0284C7')        # Sky
    DANGER = colors.HexColor('#E11D48')      # Rose

    status_config = {
        'paid': ('PAYÉE', SUCCESS, colors.HexColor('#ECFDF5')),
        'pending': ('EN ATTENTE', WARNING, colors.HexColor('#FFFBEB')),
        'partial': ('PARTIEL', INFO, colors.HexColor('#F0F9FF')),
        'overdue': ('EN RETARD', DANGER, colors.HexColor('#FFF1F2')),
    }
    status_text, status_fg, status_bg = status_config.get(invoice.status, ('EN ATTENTE', WARNING, colors.HexColor('#FFFBEB')))

    margin_left = 10 * mm
    margin_right = width - 10 * mm
    content_width = margin_right - margin_left

    # Calcul prévisionnel du nombre de pages
    num_items = len(raw_items) if raw_items else 1
    total_pages = 1 if num_items <= 11 else 1 + ((num_items - 11 + 21) // 22)

    def draw_page_decorations(page_num):
        p.setStrokeColor(BORDER)
        p.setLineWidth(0.5)
        p.line(margin_left, 13 * mm, margin_right, 13 * mm)

        p.setFont("Helvetica-Oblique", 7)
        p.setFillColor(MUTED)
        p.drawCentredString(width / 2, 9 * mm, "Merci pour votre confiance !")

        p.setFont("Helvetica", 6.5)
        company_legal = f"{company.company_name} — Facture N° {invoice.invoice_number}"
        p.drawString(margin_left, 5.5 * mm, company_legal[:50])
        if total_pages > 1:
            p.drawRightString(margin_right, 5.5 * mm, f"Page {page_num}/{total_pages}")
        else:
            p.drawRightString(margin_right, 5.5 * mm, f"Émise le {invoice.issued_date.strftime('%d/%m/%Y')}")

    # Top initial
    top = height - 10 * mm

    # ── EN-TÊTE : Logo + Entreprise (Gauche) & Facture Info (Droite) ──
    logo_drawn = False
    logo_w = 15 * mm
    logo_h = 15 * mm
    if company.logo and hasattr(company.logo, 'path'):
        try:
            p.drawImage(company.logo.path, margin_left, top - logo_h, width=logo_w, height=logo_h,
                        preserveAspectRatio=True, mask='auto')
            logo_drawn = True
        except Exception:
            logo_drawn = False

    comp_x = (margin_left + logo_w + 3 * mm) if logo_drawn else margin_left
    p.setFillColor(DARK)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(comp_x, top - 3.5 * mm, (company.company_name or 'Entreprise')[:30])

    p.setFont("Helvetica", 7)
    p.setFillColor(MUTED)
    line_y = top - 7.5 * mm
    if company.address:
        p.drawString(comp_x, line_y, company.address[:42])
        line_y -= 3.5 * mm
    contact_parts = []
    if company.phone:
        contact_parts.append(company.phone)
    if company.company_email:
        contact_parts.append(company.company_email)
    if contact_parts:
        p.drawString(comp_x, line_y, " • ".join(contact_parts)[:45])

    # Droite : Titre Facture & Numéro & Badge Statut
    p.setFillColor(PRIMARY)
    p.setFont("Helvetica-Bold", 14)
    p.drawRightString(margin_right, top - 3.5 * mm, "FACTURE")

    p.setFillColor(DARK)
    p.setFont("Helvetica-Bold", 9)
    p.drawRightString(margin_right, top - 8 * mm, invoice.invoice_number)

    p.setFont("Helvetica", 7)
    p.setFillColor(MUTED)
    p.drawRightString(margin_right, top - 12 * mm, f"Date : {invoice.issued_date.strftime('%d/%m/%Y')}")
    p.drawRightString(margin_right, top - 15.5 * mm, f"Échéance : {invoice.due_date.strftime('%d/%m/%Y')}")

    # Statut pill badge
    badge_w = 24 * mm
    badge_h = 4.5 * mm
    badge_x = margin_right - badge_w
    badge_y = top - 21.5 * mm
    p.setFillColor(status_bg)
    p.roundRect(badge_x, badge_y, badge_w, badge_h, 2, fill=1, stroke=0)
    p.setFillColor(status_fg)
    p.setFont("Helvetica-Bold", 6.5)
    p.drawCentredString(badge_x + badge_w / 2, badge_y + 1.2 * mm, status_text)

    # Séparateur fin
    sep_y = top - 24 * mm
    p.setStrokeColor(BORDER)
    p.setLineWidth(0.5)
    p.line(margin_left, sep_y, margin_right, sep_y)

    # ── BLOC CLIENT & INFOS VENTE ──
    client_card_y = sep_y - 20 * mm
    p.setFillColor(BG_LIGHT)
    p.setStrokeColor(BORDER)
    p.setLineWidth(0.5)
    p.roundRect(margin_left, client_card_y, content_width, 18 * mm, 3, fill=1, stroke=1)

    p.setFillColor(MUTED)
    p.setFont("Helvetica-Bold", 6.5)
    p.drawString(margin_left + 3 * mm, client_card_y + 13.5 * mm, "FACTURÉ À")

    p.setFillColor(DARK)
    p.setFont("Helvetica-Bold", 8.5)
    display_client = client.shop_name or client.name
    p.drawString(margin_left + 3 * mm, client_card_y + 9 * mm, display_client[:35])

    p.setFont("Helvetica", 7)
    p.setFillColor(BODY)
    c_sub = []
    if client.shop_name and client.name:
        c_sub.append(f"Contact: {client.name}")
    if client.phone:
        c_sub.append(f"Tél: {client.phone}")
    if c_sub:
        p.drawString(margin_left + 3 * mm, client_card_y + 5 * mm, " | ".join(c_sub)[:45])
    if client.address:
        p.drawString(margin_left + 3 * mm, client_card_y + 1.5 * mm, client.address[:45])

    agent_name = sale.agent.name if sale.agent else None
    if agent_name:
        p.setFillColor(MUTED)
        p.setFont("Helvetica-Bold", 6.5)
        p.drawRightString(margin_right - 3 * mm, client_card_y + 13.5 * mm, "VENDEUR")
        p.setFont("Helvetica", 7.5)
        p.setFillColor(DARK)
        p.drawRightString(margin_right - 3 * mm, client_card_y + 9 * mm, agent_name[:25])

    # ── TABLEAU DES PRODUITS (Compact et élégant) ──
    table_top = client_card_y - 4 * mm
    th_h = 5.5 * mm

    def draw_table_header(y):
        p.setFillColor(DARK)
        p.roundRect(margin_left, y - th_h, content_width, th_h, 2, fill=1, stroke=0)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 7)
        p.drawString(margin_left + 3 * mm, y - 3.8 * mm, "Désignation")
        p.drawCentredString(margin_left + 72 * mm, y - 3.8 * mm, "Qté")
        p.drawRightString(margin_left + 98 * mm, y - 3.8 * mm, "P.U.")
        p.drawRightString(margin_right - 3 * mm, y - 3.8 * mm, "Total")

    draw_table_header(table_top)
    row_y = table_top - th_h
    row_h = 6 * mm

    page_num = 1
    items = raw_items
    if not items:
        class _LegacyItem:
            quantity = sale.quantity or 1
            unit_price = sale.unit_price or Decimal('0.00')
            total_price = sale.total_price or Decimal('0.00')
            currency = sale.currency
            class product:
                name = sale.product.name if sale.product else "Produit"
        items = [_LegacyItem()]

    for i, item in enumerate(items):
        if row_y - row_h < 40 * mm:
            draw_page_decorations(page_num)
            p.showPage()
            page_num += 1
            top_new = height - 12 * mm
            p.setFont("Helvetica-Bold", 8)
            p.setFillColor(DARK)
            p.drawString(margin_left, top_new, f"Facture {invoice.invoice_number} (suite)")
            draw_table_header(top_new - 3 * mm)
            row_y = top_new - 3 * mm - th_h

        bg = BG_LIGHT if i % 2 == 0 else colors.white
        p.setFillColor(bg)
        p.rect(margin_left, row_y - row_h, content_width, row_h, fill=1, stroke=0)

        p.setStrokeColor(BORDER)
        p.setLineWidth(0.25)
        p.line(margin_left, row_y - row_h, margin_right, row_y - row_h)

        p.setFillColor(DARK)
        p.setFont("Helvetica", 7)
        p_name = item.product.name if item.product else "Produit"
        p.drawString(margin_left + 3 * mm, row_y - 4.2 * mm, p_name[:36])

        p.drawCentredString(margin_left + 72 * mm, row_y - 4.2 * mm, str(item.quantity))
        p.drawRightString(margin_left + 98 * mm, row_y - 4.2 * mm, _format_currency_amount(item.unit_price, currency))
        p.drawRightString(margin_right - 3 * mm, row_y - 4.2 * mm, _format_currency_amount(item.total_price, currency))

        row_y -= row_h

    # ── BLOC TOTAUX ET RÈGLEMENTS ──
    tot_y = row_y - 3 * mm
    box_w = 64 * mm
    box_x = margin_right - box_w

    p.setFillColor(CARD_BG)
    p.roundRect(box_x, tot_y - 7.5 * mm, box_w, 7.5 * mm, 2, fill=1, stroke=0)

    p.setFillColor(DARK)
    p.setFont("Helvetica-Bold", 8)
    p.drawString(box_x + 3 * mm, tot_y - 5.2 * mm, "TOTAL")

    p.setFillColor(PRIMARY)
    p.setFont("Helvetica-Bold", 9.5)
    p.drawRightString(margin_right - 3 * mm, tot_y - 5.2 * mm, sale.formatted_total_price)

    curr_tot_y = tot_y - 7.5 * mm

    if invoice.status != 'paid':
        curr_tot_y -= 5 * mm
        p.setFont("Helvetica", 7)
        p.setFillColor(MUTED)
        p.drawString(box_x + 3 * mm, curr_tot_y + 1.2 * mm, "Montant payé :")
        p.setFillColor(SUCCESS)
        p.setFont("Helvetica-Bold", 7.5)
        p.drawRightString(margin_right - 3 * mm, curr_tot_y + 1.2 * mm, invoice.formatted_amount_paid)

        curr_tot_y -= 5.5 * mm
        p.setFillColor(colors.HexColor('#FFF1F2'))
        p.roundRect(box_x, curr_tot_y, box_w, 5.5 * mm, 1.5, fill=1, stroke=0)
        p.setFillColor(DANGER)
        p.setFont("Helvetica-Bold", 7.5)
        p.drawString(box_x + 3 * mm, curr_tot_y + 1.5 * mm, "Reste à payer :")
        p.drawRightString(margin_right - 3 * mm, curr_tot_y + 1.5 * mm, invoice.formatted_balance_due)
    else:
        curr_tot_y -= 5 * mm
        p.setFillColor(colors.HexColor('#ECFDF5'))
        p.roundRect(box_x, curr_tot_y, box_w, 5 * mm, 1.5, fill=1, stroke=0)
        p.setFillColor(SUCCESS)
        p.setFont("Helvetica-Bold", 7)
        p.drawCentredString(box_x + box_w / 2, curr_tot_y + 1.5 * mm, "✓ FACTURE RÉGLÉE EN TOTALITÉ")

    draw_page_decorations(page_num)
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.getvalue()


def _render_invoice_pdf(invoice):
    """Réponse HTTP de téléchargement du PDF A5 de la facture."""
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


def _send_invoice_email_core(invoice, recipient_email, custom_message=""):
    """
    Génère le PDF A5 de la facture et l'envoie au client par email avec le PDF en pièce jointe.
    Retourne (success: bool, message_or_error: str).
    """
    try:
        validate_email(recipient_email)
    except ValidationError:
        return False, "Adresse email destinataire invalide."

    company = invoice.company
    sale = invoice.sale
    client = sale.client
    client_name = client.shop_name or client.name

    subject = f"Facture {invoice.invoice_number} — {company.company_name}"

    body_lines = [
        f"Bonjour {client_name},\n",
        f"Veuillez trouver ci-joint votre facture N° {invoice.invoice_number} émise le {invoice.issued_date.strftime('%d/%m/%Y')} par {company.company_name}.",
        "",
        f"• Montant total : {sale.formatted_total_price}",
    ]
    if invoice.status == 'paid':
        body_lines.append("• Statut : Payée en totalité.")
    else:
        body_lines.append(f"• Montant déjà réglé : {invoice.formatted_amount_paid}")
        body_lines.append(f"• Reste à payer : {invoice.formatted_balance_due}")
        body_lines.append(f"• Date d'échéance : {invoice.due_date.strftime('%d/%m/%Y')}")

    if custom_message and custom_message.strip():
        body_lines.extend(["", "Note complémentaire :", custom_message.strip()])

    body_lines.extend([
        "",
        "Le document officiel au format commercial compact A5 est disponible en pièce jointe.",
        "",
        "Cordialement,",
        f"{company.company_name}",
    ])
    if company.phone:
        body_lines.append(f"Tél : {company.phone}")
    if company.company_email:
        body_lines.append(f"Email : {company.company_email}")

    body = "\n".join(body_lines)

    try:
        pdf_bytes = _build_invoice_pdf_bytes(invoice)
        from_email = settings.DEFAULT_FROM_EMAIL
        reply_to = [company.company_email] if company.company_email else None

        email_msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[recipient_email],
            reply_to=reply_to,
        )
        email_msg.attach(f"Facture_{invoice.invoice_number}.pdf", pdf_bytes, 'application/pdf')
        email_msg.send(fail_silently=False)
        return True, f"Facture envoyée avec succès par email à {recipient_email}."
    except Exception as e:
        return False, f"Échec de l'envoi de l'email : {str(e)}"


@require_http_methods(["POST"])
@login_required
def send_invoice_email(request, invoice_id):
    """Envoi de facture par email déclenché par l'administrateur de l'entreprise."""
    invoice = Invoice.objects.filter(id=invoice_id, company=request.user).select_related(
        'sale', 'sale__client', 'company'
    ).first()
    if not invoice:
        return JsonResponse({"success": False, "error": "Facture introuvable"}, status=404)

    recipient_email = request.POST.get("recipient_email", "").strip()
    custom_message = request.POST.get("message", "").strip()

    if not recipient_email:
        return JsonResponse({"success": False, "error": "L'adresse email du destinataire est requise."}, status=400)

    success, msg = _send_invoice_email_core(invoice, recipient_email, custom_message)
    if success:
        return JsonResponse({"success": True, "message": msg})
    return JsonResponse({"success": False, "error": msg}, status=500)

