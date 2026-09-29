"""
Abonnement et paiement (MoneyFusion) + codes promo.
"""
import logging

from ._common import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


def _moneyfusion_configured():
    return bool(settings.MONEYFUSION_API_URL)


@require_http_methods(["GET"])
@login_required
def subscription_page(request):
    """Page dédiée à l'abonnement : statut de l'essai/abonnement + paiement MoneyFusion."""
    subscription = getattr(request.user, 'subscription', None)
    recent_payments = SubscriptionPayment.objects.filter(company=request.user)[:10]
    promo_redemptions = PromoCodeRedemption.objects.filter(company=request.user).select_related('promo_code')
    context = {
        'subscription': subscription,
        'plans': [
            {'code': 'test', 'label': 'Test', 'price': SUBSCRIPTION_PLAN_PRICES['test']},
            {'code': 'monthly', 'label': 'Mensuel', 'price': SUBSCRIPTION_PLAN_PRICES['monthly']},
            {'code': 'annual', 'label': 'Annuel', 'price': SUBSCRIPTION_PLAN_PRICES['annual']},
        ],
        'recent_payments': recent_payments,
        'promo_redemptions': promo_redemptions,
        'moneyfusion_configured': _moneyfusion_configured(),
    }
    return render(request, 'subscription.html', context)


@require_http_methods(["POST"])
@login_required
def apply_promo_code(request):
    """Applique un code promo saisi par l'entreprise depuis la page d'abonnement."""
    code = request.POST.get("code", "")
    success, message = redeem_promo_code(request.user, code)
    if success:
        return JsonResponse({"success": True, "message": message})
    return JsonResponse({"success": False, "error": message}, status=400)


@require_http_methods(["GET"])
@staff_member_required
def promo_codes_admin(request):
    """Liste des codes promo + formulaire de génération rapide (réservé au staff)."""
    codes = PromoCode.objects.all().prefetch_related('redemptions')
    return render(request, 'promo_codes_admin.html', {'codes': codes})


@require_http_methods(["POST"])
@staff_member_required
def create_promo_code(request):
    """Génère un nouveau code promo avec la durée choisie."""
    try:
        duration_days = int(request.POST.get("duration_days", "0"))
    except (TypeError, ValueError):
        duration_days = 0
    if duration_days <= 0:
        return JsonResponse({"success": False, "error": "La durée doit être un nombre de jours positif."}, status=400)

    note = request.POST.get("note", "").strip()[:255]
    custom_code = request.POST.get("code", "").strip().upper()

    max_redemptions_raw = request.POST.get("max_redemptions", "").strip()
    max_redemptions = None
    if max_redemptions_raw:
        try:
            max_redemptions = int(max_redemptions_raw)
            if max_redemptions <= 0:
                max_redemptions = None
        except ValueError:
            max_redemptions = None

    valid_until_raw = request.POST.get("valid_until", "").strip()
    valid_until = None
    if valid_until_raw:
        # Format attendu depuis <input type="date"> : YYYY-MM-DD
        try:
            from datetime import datetime
            valid_until = timezone.make_aware(datetime.strptime(valid_until_raw, "%Y-%m-%d"))
        except ValueError:
            valid_until = None

    kwargs = {
        'duration_days': duration_days,
        'note': note,
        'max_redemptions': max_redemptions,
        'valid_until': valid_until,
    }
    if custom_code:
        if PromoCode.objects.filter(code__iexact=custom_code).exists():
            return JsonResponse({"success": False, "error": "Ce code existe déjà."}, status=400)
        kwargs['code'] = custom_code

    promo = PromoCode.objects.create(**kwargs)
    return JsonResponse({"success": True, "code": promo.code, "id": promo.id})


@require_http_methods(["POST"])
@staff_member_required
def toggle_promo_code(request, promo_id):
    """Active/désactive un code promo (bascule)."""
    try:
        promo = PromoCode.objects.get(id=promo_id)
    except PromoCode.DoesNotExist:
        return JsonResponse({"success": False, "error": "Code promo introuvable."}, status=404)
    promo.is_active = not promo.is_active
    promo.save(update_fields=['is_active'])
    return JsonResponse({"success": True, "is_active": promo.is_active})


@require_http_methods(["POST"])
@login_required
def initiate_subscription_payment(request):
    """Crée une transaction MoneyFusion pour le plan choisi et renvoie l'URL de paiement
    vers laquelle le navigateur doit être redirigé (intégration par redirection)."""
    if not _moneyfusion_configured():
        return JsonResponse({
            "success": False,
            "error": "Le paiement en ligne n'est pas encore configuré. Contactez l'administrateur.",
        }, status=503)

    plan = request.POST.get("plan")
    if plan not in dict(SUBSCRIPTION_PLAN_CHOICES).keys():
        return JsonResponse({"success": False, "error": "Plan invalide"}, status=400)

    subscription, _ = Subscription.objects.get_or_create(
        company=request.user,
        defaults={'plan': plan, 'trial_end_date': timezone.now() + timezone.timedelta(days=TRIAL_DURATION_DAYS)},
    )

    amount = int(SUBSCRIPTION_PLAN_PRICES[plan])
    transaction_id = f"SUB-{request.user.id}-{uuid.uuid4().hex[:12]}"

    payment = SubscriptionPayment.objects.create(
        company=request.user,
        plan=plan,
        amount=amount,
        transaction_id=transaction_id,
        status='pending',
    )

    user = request.user
    plan_label = dict(SUBSCRIPTION_PLAN_CHOICES).get(plan)

    payload = {
        "totalPrice": amount,
        "article": [{f"Abonnement {plan_label}": amount}],
        "numeroSend": (user.phone or "0000000000").replace(" ", ""),
        "nomclient": user.company_name or user.email or "Client",
        "personal_Info": [{"userId": str(user.id), "orderId": transaction_id}],
        "return_url": settings.SITE_BASE_URL.rstrip('/') + reverse('moneyfusion_return'),
        "webhook_url": settings.SITE_BASE_URL.rstrip('/') + reverse('moneyfusion_webhook'),
    }

    try:
        response = http_requests.post(settings.MONEYFUSION_API_URL, json=payload, timeout=20)
        data = response.json()
    except (http_requests.RequestException, ValueError):
        payment.status = 'failed'
        payment.save(update_fields=['status', 'updated_at'])
        return JsonResponse({"success": False, "error": "Impossible de contacter MoneyFusion. Réessayez."}, status=502)

    if not data.get("statut"):
        payment.status = 'failed'
        payment.save(update_fields=['status', 'updated_at'])
        return JsonResponse({"success": False, "error": data.get("message") or "Échec de l'initialisation du paiement."}, status=400)

    provider_token = data.get("token", "")
    payment.provider_token = provider_token
    payment.save(update_fields=['provider_token', 'updated_at'])

    payment_url = data.get("url")
    return JsonResponse({"success": True, "payment_url": payment_url, "transaction_id": transaction_id})


def _verify_and_apply_payment(payment):
    """Vérifie une transaction auprès de MoneyFusion et applique le résultat (idempotent).
    `payment` est déjà chargé (SubscriptionPayment) — évite une seconde requête en base."""
    if payment is None or payment.status == 'success' or not payment.provider_token:
        return payment  # rien à faire (déjà traité, ou pas encore de token MoneyFusion)

    status_url = settings.MONEYFUSION_STATUS_CHECK_TEMPLATE.format(token=payment.provider_token)
    try:
        response = http_requests.get(status_url, timeout=20)
        response.raise_for_status()
        data = response.json()
    except (http_requests.RequestException, ValueError) as exc:
        logger.error(
            "Échec de la vérification MoneyFusion pour le paiement %s (token=%s) via %s : %s",
            payment.transaction_id, payment.provider_token, status_url, exc,
        )
        return payment

    result = data.get("data", {})
    provider_status = result.get("statut")  # "paid" | "pending" | "failed" | "no paid"
    payment.payment_method = result.get("moyen", "") or payment.payment_method
    payment.operator_id = result.get("numeroTransaction", "") or payment.operator_id

    if provider_status == "paid":
        payment.status = 'success'
        payment.save(update_fields=['status', 'payment_method', 'operator_id', 'updated_at'])
        subscription, _ = Subscription.objects.get_or_create(
            company=payment.company,
            defaults={'plan': payment.plan},
        )
        subscription.plan = payment.plan
        subscription.extend_after_payment()
    elif provider_status in ("failed", "no paid"):
        payment.status = 'failed'
        payment.save(update_fields=['status', 'payment_method', 'operator_id', 'updated_at'])
    else:
        payment.save(update_fields=['payment_method', 'operator_id', 'updated_at'])

    return payment


@csrf_exempt
@require_http_methods(["POST"])
def moneyfusion_webhook(request):
    """Webhook appelé par les serveurs de MoneyFusion (webhook_url fourni à l'initialisation)
    à chaque changement de statut."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        body = request.POST

    provider_token = body.get("tokenPay") or body.get("token")
    event = body.get("event")
    raw_status = body.get("statut")

    payment = None
    if provider_token:
        payment = SubscriptionPayment.objects.select_related('company', 'company__subscription').filter(
            provider_token=provider_token
        ).first()

    # Si non trouvé par token, chercher par orderId dans personal_Info
    if payment is None and isinstance(body.get("personal_Info"), list) and body["personal_Info"]:
        order_id = body["personal_Info"][0].get("orderId")
        if order_id:
            payment = SubscriptionPayment.objects.select_related('company', 'company__subscription').filter(
                transaction_id=order_id
            ).first()

    if payment is None:
        return HttpResponse("Transaction inconnue", status=404)

    # Associer le token s'il manquait
    if provider_token and not payment.provider_token:
        payment.provider_token = provider_token
        payment.save(update_fields=['provider_token', 'updated_at'])

    # Si le webhook notifie explicitement le succès
    if event == "payin.session.completed" or raw_status == "paid":
        payment.status = 'success'
        if body.get("numeroTransaction"):
            payment.operator_id = body.get("numeroTransaction")
        if body.get("moyen"):
            payment.payment_method = body.get("moyen")
        payment.save(update_fields=['status', 'payment_method', 'operator_id', 'updated_at'])
        subscription, _ = Subscription.objects.get_or_create(
            company=payment.company,
            defaults={'plan': payment.plan, 'trial_end_date': timezone.now()},
        )
        subscription.plan = payment.plan
        subscription.extend_after_payment()
        return HttpResponse("OK")
    elif event == "payin.session.cancelled" or raw_status in ("failure", "failed", "no paid"):
        payment.status = 'failed'
        payment.save(update_fields=['status', 'updated_at'])
        return HttpResponse("OK")

    # Sinon revérifier via l'API MoneyFusion
    _verify_and_apply_payment(payment)
    return HttpResponse("OK")


@require_http_methods(["GET", "POST"])
@login_required
def moneyfusion_return(request):
    """Page où le client est redirigé après avoir payé (return_url — MoneyFusion y ajoute ?token=... ou ?tokenPay=...)."""
    provider_token = (
        request.GET.get("token")
        or request.GET.get("tokenPay")
        or request.POST.get("token")
        or request.POST.get("tokenPay")
    )

    payment = None
    if provider_token:
        payment = SubscriptionPayment.objects.select_related('company', 'company__subscription').filter(
            company=request.user, provider_token=provider_token
        ).first()
    if payment is None:
        payment = SubscriptionPayment.objects.filter(company=request.user).order_by('-created_at').first()

    if payment and provider_token and not payment.provider_token:
        payment.provider_token = provider_token
        payment.save(update_fields=['provider_token', 'updated_at'])

    # MoneyFusion ne garantit pas l'ordre webhook/retour : on revérifie ici aussi par sécurité.
    if payment and payment.status == 'pending':
        payment = _verify_and_apply_payment(payment)

    return render(request, 'subscription_return.html', {'payment': payment})