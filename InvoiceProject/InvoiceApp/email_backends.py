"""
Backend email Django pour l'API transactionnelle v3 de Brevo.
Utilise `requests` (déjà présent dans requirements.txt) afin de ne dépendre
d'aucun paquet tiers supplémentaire.
"""
import base64
import json
from email.mime.base import MIMEBase
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


def _decode_brevo_key(raw_value):
    val = (raw_value or "").strip().strip("\"'")
    if val.startswith("eyJ"):
        try:
            decoded = json.loads(base64.b64decode(val).decode("utf-8"))
            if isinstance(decoded, dict) and decoded.get("api_key"):
                return str(decoded["api_key"]).strip()
        except Exception:
            pass
    return val


def _format_address(raw_addr):
    name, addr = parseaddr(raw_addr or "")
    addr = (addr or raw_addr or "").strip()
    if not addr:
        return None
    if name:
        return {"email": addr, "name": name}
    return {"email": addr}


def _format_address_list(addresses):
    items = []
    for raw in addresses or []:
        formatted = _format_address(raw)
        if formatted:
            items.append(formatted)
    return items


class BrevoEmailBackend(BaseEmailBackend):
    """Envoie les emails Django (EmailMessage / EmailMultiAlternatives) via l'API Brevo v3."""

    def __init__(self, fail_silently=False, api_key=None, api_url=None, timeout=None, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = _decode_brevo_key(
            api_key if api_key is not None else getattr(settings, "BREVO_API_KEY", "")
        )
        base_url = (
            api_url
            or getattr(settings, "BREVO_API_URL", "https://api.brevo.com/v3/smtp/email")
        ).rstrip("/")
        if not base_url.endswith("/smtp/email"):
            base_url = f"{base_url}/smtp/email"
        self.api_url = base_url
        self.timeout = timeout if timeout is not None else getattr(settings, "BREVO_API_TIMEOUT", 20)

    def _build_payload(self, email_message):
        sender = _format_address(email_message.from_email or settings.DEFAULT_FROM_EMAIL)
        if not sender:
            raise ValueError("Adresse d'expédition (DEFAULT_FROM_EMAIL) manquante.")

        to_list = _format_address_list(email_message.to)
        if not to_list:
            raise ValueError("Aucun destinataire spécifié.")

        payload = {
            "sender": sender,
            "to": to_list,
            "subject": email_message.subject or "",
        }

        cc_list = _format_address_list(getattr(email_message, "cc", None))
        if cc_list:
            payload["cc"] = cc_list

        bcc_list = _format_address_list(getattr(email_message, "bcc", None))
        if bcc_list:
            payload["bcc"] = bcc_list

        reply_to_list = _format_address_list(getattr(email_message, "reply_to", None))
        if reply_to_list:
            payload["replyTo"] = reply_to_list[0]

        content_subtype = getattr(email_message, "content_subtype", "plain")
        body = email_message.body or ""
        if content_subtype == "html":
            payload["htmlContent"] = body
        elif body:
            payload["textContent"] = body

        for alt_content, alt_mimetype in getattr(email_message, "alternatives", []) or []:
            if alt_mimetype == "text/html" and alt_content:
                payload["htmlContent"] = alt_content

        attachments = []
        for att in getattr(email_message, "attachments", []) or []:
            if isinstance(att, MIMEBase):
                filename = att.get_filename() or "attachment"
                raw_bytes = att.get_payload(decode=True) or b""
            else:
                filename, content, _mimetype = att
                if isinstance(content, str):
                    raw_bytes = content.encode("utf-8")
                else:
                    raw_bytes = bytes(content or b"")
            attachments.append({
                "name": filename or "attachment",
                "content": base64.b64encode(raw_bytes).decode("ascii"),
            })
        if attachments:
            payload["attachment"] = attachments

        return payload

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if not self.fail_silently:
                raise RuntimeError("BREVO_API_KEY non configurée (401 Unauthorized).")
            return 0

        sent_count = 0
        headers = {
            "api-key": self.api_key,
            "accept": "application/json",
            "content-type": "application/json",
        }

        for message in email_messages:
            try:
                payload = self._build_payload(message)
                resp = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if resp.status_code not in (200, 201, 202):
                    raise RuntimeError(f"Brevo API {resp.status_code}: {resp.text}")
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        message.brevo_message_id = data.get("messageId")
                except ValueError:
                    pass
                sent_count += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent_count
