"""
Vues de gestion WhatsApp Business Cloud API :
- Webhook officiel pour les statuts de livraison (sent, delivered, read)
- Declenchement de l'envoi serveur pour admin et vendeur
"""
import json
from ._common import *  # noqa: F401,F403
from .vendor import agent_login_required
from ..services.whatsapp import (
    is_whatsapp_cloud_configured,
    clean_phone_for_whatsapp,
    send_invoice_via_cloud_api,
)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    """
    Point de terminaison Webhook officiel pour Meta WhatsApp Cloud API.
    - GET: Verification initiale du challenge Meta (hub.challenge)
    - POST: Reception des accusés de reception et statuts (sent, delivered, read, failed)
    """
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        expected_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
        if mode == "subscribe" and token == expected_token:
            return HttpResponse(challenge, content_type="text/plain", status=200)
        return HttpResponse("Forbidden", status=403)

    # POST : Reception des evenements de statut
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"status": "bad_request"}, status=400)

    entries = data.get("entry", [])
    for entry in entries:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            statuses = value.get("statuses", [])
            for st in statuses:
                wamid = st.get("id")
                new_status = st.get("status")  # sent, delivered, read, failed
                if not wamid or not new_status:
                    continue

                invoice = Invoice.objects.filter(whatsapp_message_id=wamid).first()
                if not invoice:
                    continue

                invoice.whatsapp_delivery_status = new_status
                now = timezone.now()
                update_fields = ['whatsapp_delivery_status']

                if new_status == 'delivered' and not invoice.whatsapp_delivered_at:
                    invoice.whatsapp_delivered_at = now
                    update_fields.append('whatsapp_delivered_at')
                elif new_status == 'read':
                    if not invoice.whatsapp_delivered_at:
                        invoice.whatsapp_delivered_at = now
                        update_fields.append('whatsapp_delivered_at')
                    if not invoice.whatsapp_read_at:
                        invoice.whatsapp_read_at = now
                        update_fields.append('whatsapp_read_at')

                invoice.save(update_fields=update_fields)

    return JsonResponse({"status": "received"}, status=200)


@require_http_methods(["POST"])
@login_required
def send_invoice_whatsapp_api(request, invoice_id):
    """
    Envoi de la facture via WhatsApp initié par l'administrateur.
    Si WhatsApp Cloud API est configuré -> envoi direct serveur.
    Sinon -> signal 'client_fallback' pour ouverture wa.me / Web Share sans bloquer l'utilisateur.
    """
    invoice = Invoice.objects.filter(id=invoice_id, company=request.user).select_related(
        'sale', 'sale__client', 'company'
    ).first()
    if not invoice:
        return JsonResponse({"success": False, "error": "Facture introuvable"}, status=404)

    recipient_phone = request.POST.get("phone", "").strip() or (invoice.sale.client.phone if invoice.sale.client else "")
    custom_message = request.POST.get("message", "").strip()

    if not is_whatsapp_cloud_configured():
        return JsonResponse({
            "success": True,
            "mode": "client_fallback",
            "message": "API Cloud non configurée. Bascule automatique vers le partage direct."
        })

    success, result = send_invoice_via_cloud_api(invoice, recipient_phone, custom_message)
    if success:
        return JsonResponse({
            "success": True,
            "mode": "cloud_api",
            "message": "Facture expédiée avec succès via WhatsApp Business !",
            "message_id": result,
            "whatsapp_status": invoice.whatsapp_delivery_status,
            "status_label": invoice.whatsapp_status_label
        })
    return JsonResponse({
        "success": False,
        "mode": "cloud_api",
        "error": result
    }, status=500)


@require_http_methods(["POST"])
@agent_login_required
def vendor_send_invoice_whatsapp_api(request, invoice_id):
    """
    Envoi de la facture via WhatsApp initié par un vendeur (agent).
    Si WhatsApp Cloud API est configuré -> envoi direct serveur.
    Sinon -> signal 'client_fallback' pour ouverture wa.me / Web Share.
    """
    invoice = Invoice.objects.filter(id=invoice_id, company=request.agent.company).select_related(
        'sale', 'sale__client', 'company'
    ).first()
    if not invoice:
        return JsonResponse({"success": False, "error": "Facture introuvable"}, status=404)

    recipient_phone = request.POST.get("phone", "").strip() or (invoice.sale.client.phone if invoice.sale.client else "")
    custom_message = request.POST.get("message", "").strip()

    if not is_whatsapp_cloud_configured():
        return JsonResponse({
            "success": True,
            "mode": "client_fallback",
            "message": "API Cloud non configurée. Bascule automatique vers le partage direct."
        })

    success, result = send_invoice_via_cloud_api(invoice, recipient_phone, custom_message)
    if success:
        return JsonResponse({
            "success": True,
            "mode": "cloud_api",
            "message": "Facture expédiée avec succès via WhatsApp Business !",
            "message_id": result,
            "whatsapp_status": invoice.whatsapp_delivery_status,
            "status_label": invoice.whatsapp_status_label
        })
    return JsonResponse({
        "success": False,
        "mode": "cloud_api",
        "error": result
    }, status=500)
