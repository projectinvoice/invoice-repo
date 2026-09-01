"""
Pages publiques liées depuis le footer de la landing page :
Centre d'aide, Contact, Statut du service, Conditions d'utilisation, Confidentialité.
"""
from ._common import *  # noqa: F401,F403
from django.db import connection
from django.core.mail import EmailMessage


def help_center(request):
    """Centre d'aide : FAQ organisée par thème, en pur contenu statique."""
    return render(request, 'help_center.html')


@require_http_methods(["GET", "POST"])
def contact(request):
    """Formulaire de contact public : envoie un email à l'équipe support."""
    sent = False
    error = None

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()

        if not name or not email or not message:
            error = "Merci de renseigner votre nom, votre email et votre message."
        else:
            full_subject = f"[Contact InvoiceApp] {subject}" if subject else "[Contact InvoiceApp] Nouveau message"
            body = (
                f"Nouveau message depuis le formulaire de contact public.\n\n"
                f"Nom : {name}\n"
                f"Email : {email}\n"
                f"Sujet : {subject or '(non précisé)'}\n\n"
                f"Message :\n{message}\n"
            )
            try:
                email_msg = EmailMessage(
                    subject=full_subject,
                    body=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[settings.SUPPORT_EMAIL],
                    reply_to=[email],
                )
                email_msg.send(fail_silently=False)
                sent = True
            except Exception:
                error = "L'envoi a échoué. Réessayez plus tard ou écrivez-nous directement à " + settings.SUPPORT_EMAIL

    return render(request, 'contact.html', {
        'sent': sent,
        'error': error,
        'support_email': settings.SUPPORT_EMAIL,
    })


def service_status(request):
    """Statut du service : vérifie en direct la disponibilité des composants clés
    (base de données, assistant IA, paiement des abonnements) plutôt que d'afficher
    une page purement statique."""

    # Base de données : une requête triviale suffit à vérifier la connexion
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        db_ok = False

    components = [
        {
            'name': 'Application web',
            'status': 'operational',
            'detail': 'Pages et connexion utilisateur',
        },
        {
            'name': 'Base de données',
            'status': 'operational' if db_ok else 'down',
            'detail': 'Stockage des ventes, clients, factures et stock',
        },
        {
            'name': 'Assistant IA',
            'status': 'operational' if settings.GEMINI_API_KEY else 'disabled',
            'detail': 'Assistant conversationnel Gemini' if settings.GEMINI_API_KEY else "Non configuré sur cette instance",
        },
        {
            'name': 'Paiement des abonnements',
            'status': 'operational' if settings.MONEYFUSION_API_URL else 'disabled',
            'detail': 'Paiement en ligne via MoneyFusion' if settings.MONEYFUSION_API_URL else "Non configuré sur cette instance",
        },
        {
            'name': 'Envoi d\'emails',
            'status': 'operational' if 'console' not in settings.EMAIL_BACKEND else 'degraded',
            'detail': 'Emails transactionnels (activation, réinitialisation...)' if 'console' not in settings.EMAIL_BACKEND
                       else 'Mode développement : emails affichés dans les logs serveur, non réellement envoyés',
        },
    ]

    all_operational = all(c['status'] == 'operational' for c in components if c['status'] != 'disabled')

    return render(request, 'service_status.html', {
        'components': components,
        'all_operational': all_operational,
        'checked_at': timezone.now(),
    })


def terms_of_service(request):
    """Conditions d'utilisation (contenu statique)."""
    return render(request, 'terms.html', {'last_updated': '1er septembre 2026'})


def privacy_policy(request):
    """Politique de confidentialité (contenu statique)."""
    return render(request, 'privacy.html', {'last_updated': '1er septembre 2026'})
