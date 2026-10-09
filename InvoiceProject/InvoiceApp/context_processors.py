from django.conf import settings


def subscription_context(request):
    """Injecte l'état de l'abonnement de l'entreprise connectée dans tous les templates,
    pour permettre de griser les boutons/liens quand l'accès est bloqué."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    subscription = getattr(user, 'subscription', None)
    if subscription is None:
        return {}

    return {
        'subscription': subscription,
        'subscription_status': subscription.status,
        'subscription_blocked': subscription.is_blocked,
        'subscription_days_left': subscription.days_left,
        'subscription_expiry_date': subscription.access_expiry_date,
        'subscription_plan_price': subscription.price,
        'subscription_access_days_remaining': subscription.access_days_remaining,
    }


def whatsapp_context(request):
    """
    Injecte la visibilité du canal WhatsApp dans tous les templates.
    La visibilité de la partie WhatsApp est conditionnée par la présence
    d'une clé API WhatsApp (WHATSAPP_TOKEN) dans les variables d'environnement.
    """
    token = getattr(settings, 'WHATSAPP_TOKEN', '') or ''
    return {
        'whatsapp_enabled': bool(str(token).strip()),
    }

