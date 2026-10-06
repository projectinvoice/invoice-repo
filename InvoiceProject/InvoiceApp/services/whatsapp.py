"""
Service d'integration officiel avec WhatsApp Business Cloud API (Meta Graph API).
Permet l'envoi direct de factures PDF A5 et le suivi des accreditations (envoye, remis, lu).
"""
import re
import requests
from django.conf import settings
from django.utils import timezone


def is_whatsapp_cloud_configured():
    """Verifie si les identifiants officiels WhatsApp Cloud API sont renseignes."""
    token = getattr(settings, 'WHATSAPP_TOKEN', '') or ''
    phone_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '') or ''
    return bool(token.strip() and phone_id.strip())


def clean_phone_for_whatsapp(phone):
    """
    Nettoie et formate un numero de telephone pour l'API WhatsApp (format international sans '+').
    Gere l'international direct, Burkina Faso (8 chiffres), Senegal (9 chiffres) et Cote d'Ivoire (10 chiffres).
    """
    if not phone:
        return ''
    cleaned = re.sub(r'[\s\-\(\)\.]', '', str(phone).strip())
    if cleaned.startswith('+'):
        cleaned = cleaned[1:]
    elif cleaned.startswith('00'):
        cleaned = cleaned[2:]

    # Deja au format international (11 a 15 chiffres sans '0' initial)
    if len(cleaned) >= 11 and not cleaned.startswith('0'):
        return cleaned

    # Cas local Burkina Faso: 8 chiffres debutant par 0, 5, 6, 7
    if len(cleaned) == 8 and re.match(r'^[0567]\d{7}$', cleaned):
        return '226' + cleaned

    # Cas local Senegal: 9 chiffres debutant par 70, 75, 76, 77, 78
    if len(cleaned) == 9 and re.match(r'^(70|75|76|77|78)\d{7}$', cleaned):
        return '221' + cleaned

    # Cas local Cote d'Ivoire: 10 chiffres debutant par 01, 05, 07
    if len(cleaned) == 10 and re.match(r'^(01|05|07)\d{8}$', cleaned):
        return '225' + cleaned

    return cleaned


def upload_media_to_meta(file_bytes, filename="facture.pdf", mime_type="application/pdf"):
    """
    Televerse le PDF de la facture sur les serveurs de Meta (WhatsApp Media API).
    Retourne l'ID du media genere (media_id).
    """
    token = settings.WHATSAPP_TOKEN
    phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    version = getattr(settings, 'WHATSAPP_API_VERSION', 'v18.0')
    url = f"https://graph.facebook.com/{version}/{phone_id}/media"

    headers = {
        "Authorization": f"Bearer {token}"
    }
    files = {
        "file": (filename, file_bytes, mime_type)
    }
    data = {
        "messaging_product": "whatsapp",
        "type": mime_type
    }

    response = requests.post(url, headers=headers, files=files, data=data, timeout=20)
    res_json = response.json()
    if response.status_code not in (200, 201) or "id" not in res_json:
        error_detail = res_json.get("error", {}).get("message", response.text)
        raise RuntimeError(f"Erreur televersement Meta: {error_detail}")

    return res_json["id"]


def send_invoice_via_cloud_api(invoice, recipient_phone, custom_message=""):
    """
    Genere le PDF A5 de la facture, le televerse sur Meta Media API,
    puis envoie le document WhatsApp au client avec le message d'accompagnement.
    Retourne (success: bool, message_or_error: str).
    """
    if not is_whatsapp_cloud_configured():
        return False, "WhatsApp Cloud API non configuree (WHATSAPP_TOKEN ou WHATSAPP_PHONE_NUMBER_ID manquant)."

    cleaned_phone = clean_phone_for_whatsapp(recipient_phone)
    if not cleaned_phone or len(cleaned_phone) < 8:
        return False, "Numero de telephone destinataire invalide."

    # Import differe pour eviter les dependances circulaires
    from ..views.invoices import _build_invoice_pdf_bytes

    company = invoice.company
    sale = invoice.sale
    client = sale.client
    client_name = client.shop_name or client.name

    filename = f"Facture_{invoice.invoice_number}.pdf"

    try:
        # 1. Generation du PDF A5
        pdf_bytes = _build_invoice_pdf_bytes(invoice)

        # 2. Upload du media chez Meta
        media_id = upload_media_to_meta(pdf_bytes, filename=filename, mime_type="application/pdf")

        # 3. Preparation de la legende / message texte
        caption_lines = [
            f"Bonjour {client_name},",
            f"Voici votre facture {invoice.invoice_number} emise par {company.company_name}.",
            f"• Total : {sale.formatted_total_price}",
        ]
        if invoice.status == 'paid':
            caption_lines.append("• Statut : Payee en totalite ✓")
        else:
            caption_lines.append(f"• Reste a payer : {invoice.formatted_balance_due}")

        if custom_message and custom_message.strip():
            caption_lines.append(f"Note : {custom_message.strip()}")

        caption_lines.append("Facture commerciale compacte A5 en piece jointe.")
        caption = "\n".join(caption_lines)[:1024]  # Limite Meta pour caption

        # 4. Envoi du message document
        token = settings.WHATSAPP_TOKEN
        phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
        version = getattr(settings, 'WHATSAPP_API_VERSION', 'v18.0')
        url = f"https://graph.facebook.com/{version}/{phone_id}/messages"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cleaned_phone,
            "type": "document",
            "document": {
                "id": media_id,
                "caption": caption,
                "filename": filename
            }
        }

        response = requests.post(url, headers=headers, json=payload, timeout=20)
        res_json = response.json()

        if response.status_code not in (200, 201) or "messages" not in res_json:
            error_detail = res_json.get("error", {}).get("message", response.text)
            return False, f"Erreur API Meta WhatsApp: {error_detail}"

        message_id = res_json["messages"][0]["id"]

        # 5. Mise a jour du suivi en base de donnees
        invoice.whatsapp_message_id = message_id
        invoice.whatsapp_delivery_status = 'sent'
        invoice.save(update_fields=['whatsapp_message_id', 'whatsapp_delivery_status'])

        return True, message_id

    except Exception as e:
        return False, f"Echec de l'envoi WhatsApp: {str(e)}"
