from django.shortcuts import redirect
from django.http import JsonResponse
from django.urls import reverse


# Chemins exacts toujours accessibles (le "dashboard" en lecture, entreprise ou vendeur)
ALLOWED_EXACT_PATHS_WHEN_BLOCKED = {
    '/dashboard/',
    '/vendeur/',
}

# Préfixes toujours accessibles : abonnement/paiement, déconnexion, admin, fichiers statiques
ALLOWED_PATH_PREFIXES_WHEN_BLOCKED = [
    '/api/dashboard/',
    '/subscription/',
    '/admin-tools/',
    '/logout/',
    '/vendeur/logout/',
    '/admin/',
    '/static/',
    '/media/',
]


class SubscriptionAccessMiddleware:
    """Quand l'essai gratuit de 7 jours est terminé et qu'aucun paiement n'est actif,
    l'entreprise (et ses vendeurs) ne peuvent plus consulter que le dashboard : toute
    autre page applicative redirige vers le dashboard (GET) ou renvoie une erreur 402 (POST/API)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        subscription = self._get_subscription(request)

        if subscription is not None and subscription.is_blocked:
            path = request.path
            is_allowed = (
                path in ALLOWED_EXACT_PATHS_WHEN_BLOCKED
                or any(path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES_WHEN_BLOCKED)
            )
            if not is_allowed:
                if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Votre période d'essai est terminée. Abonnez-vous pour continuer à utiliser cette fonctionnalité.",
                            "subscription_expired": True,
                        },
                        status=402,
                    )
                target = 'vendor_dashboard' if request.session.get('agent_id') else 'dashboard'
                return redirect(target)

        return self.get_response(request)

    def _get_subscription(self, request):
        # Entreprise connectée directement (compte admin)
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            return getattr(user, 'subscription', None)

        # Vendeur connecté via le code entreprise + PIN (session, pas de django auth)
        agent_id = request.session.get('agent_id')
        if agent_id:
            from .models import Agent
            agent = Agent.objects.filter(id=agent_id, is_active=True).select_related('company__subscription').first()
            if agent:
                return getattr(agent.company, 'subscription', None)

        return None
