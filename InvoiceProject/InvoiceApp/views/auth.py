"""
Authentification entreprise : inscription, connexion, activation, mot de passe.
"""
from ._common import *  # noqa: F401,F403
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape


def _send_transactional_email(subject, to_email, greeting_name, intro_html, cta_label, cta_url, outro_html, text_body):
    """Envoie un email avec une version HTML (lien cliquable sous forme de bouton) et
    une version texte en secours pour les clients mail qui n'affichent pas le HTML."""
    html_body = f"""\
<div style="font-family: Arial, Helvetica, sans-serif; max-width: 480px; margin: 0 auto; color: #1f2937;">
  <p>Bonjour {escape(greeting_name)},</p>
  <p>{intro_html}</p>
  <p style="text-align: center; margin: 32px 0;">
    <a href="{escape(cta_url)}"
       style="background-color: #2563eb; color: #ffffff; text-decoration: none;
              padding: 12px 24px; border-radius: 6px; font-weight: bold; display: inline-block;">
      {escape(cta_label)}
    </a>
  </p>
  <p style="font-size: 13px; color: #6b7280;">
    Si le bouton ne fonctionne pas, copiez-collez ce lien dans votre navigateur :<br>
    <a href="{escape(cta_url)}" style="color: #2563eb; word-break: break-all;">{escape(cta_url)}</a>
  </p>
  <p>{outro_html}</p>
  <p>Cordialement,<br>L'équipe InvoiceApp</p>
</div>
"""
    msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [to_email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)


def landing(request):
    """Landing page - visible to all visitors"""
    return render(request, 'landing.html')


def _send_activation_email(user):
    """Envoie l'email contenant le lien d'activation du compte entreprise."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    activation_link = settings.SITE_BASE_URL.rstrip('/') + reverse('activate_account', kwargs={'uidb64': uid, 'token': token})

    subject = "Activez votre compte InvoiceApp"
    text_body = (
        f"Bonjour {user.company_name},\n\n"
        f"Votre compte InvoiceApp a bien été créé. Il ne vous reste qu'une étape avant de "
        f"pouvoir commencer à l'utiliser : confirmer votre adresse email.\n\n"
        f"Activez votre compte via ce lien :\n{activation_link}\n\n"
        f"Ce lien est valable 24 heures.\n\n"
        f"Si vous n'êtes pas à l'origine de cette inscription, vous pouvez ignorer cet email "
        f"en toute sécurité.\n\n"
        f"Cordialement,\nL'équipe InvoiceApp\n"
    )
    _send_transactional_email(
        subject=subject,
        to_email=user.email,
        greeting_name=user.company_name,
        intro_html="Votre compte InvoiceApp a bien été créé. Il ne vous reste qu'une étape avant de "
                    "pouvoir commencer à l'utiliser : confirmer votre adresse email.",
        cta_label="Activer mon compte",
        cta_url=activation_link,
        outro_html="Ce lien est valable 24 heures. Si vous n'êtes pas à l'origine de cette inscription, "
                    "vous pouvez ignorer cet email en toute sécurité.",
        text_body=text_body,
    )


@require_http_methods(["GET", "POST"])
def register_company(request):
    if request.method == "POST":
        company_name = request.POST.get("company_name")
        email = request.POST.get("email")
        password = request.POST.get("password")
        password_confirm = request.POST.get("password_confirm")
        phone = request.POST.get("phone", "")
        address = request.POST.get("address", "")
        default_currency = request.POST.get("default_currency", "EUR")
        subscription_plan = request.POST.get("subscription_plan", "monthly")
        promo_code_input = request.POST.get("promo_code", "").strip()
        logo = request.FILES.get("logo")

        if not company_name or not email or not password:
            return JsonResponse({"success": False, "error": "company_name, email et password obligatoires"}, status=400)
        if password != password_confirm:
            return JsonResponse({"success": False, "error": "Les mots de passe ne correspondent pas"}, status=400)
        if User.objects.filter(username=email).exists() or User.objects.filter(company_email=email).exists():
            return JsonResponse({"success": False, "error": "Un utilisateur avec cet email existe déjà"}, status=400)

        try:
            validate_password(password)
        except ValidationError as e:
            return JsonResponse({"success": False, "error": " ".join(e.messages)}, status=400)

        valid_currencies = dict(CURRENCY_CHOICES).keys()
        if default_currency not in valid_currencies:
            default_currency = "EUR"

        if subscription_plan not in dict(SUBSCRIPTION_PLAN_CHOICES).keys():
            subscription_plan = "monthly"

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            company_name=company_name,
            company_email=email,
            phone=phone,
            address=address,
            default_currency=default_currency,
            logo=logo,
            is_active=False,
        )
        Subscription.objects.create(
            company=user,
            plan=subscription_plan,
            trial_end_date=timezone.now() + timezone.timedelta(days=TRIAL_DURATION_DAYS),
        )

        promo_message = None
        if promo_code_input:
            promo_success, promo_message = redeem_promo_code(user, promo_code_input)
            # À l'inscription initiale, le compte reste en attente de validation email
            if user.is_active:
                user.is_active = False
                user.save(update_fields=['is_active'])

        try:
            _send_activation_email(user)
            activation_email_sent = True
        except Exception:
            # On ne bloque jamais la création du compte si l'envoi d'email échoue,
            # mais on informe le front pour proposer un renvoi manuel.
            activation_email_sent = False

        return JsonResponse({
            "success": True,
            "message": "Compte créé. Vérifiez votre boîte mail pour activer votre compte.",
            "user_id": user.id,
            "promo_message": promo_message,
            "activation_email_sent": activation_email_sent,
        })

    return render(request, 'register.html')


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        if not email or not password:
            return JsonResponse({"success": False, "error": "email et password requis"}, status=400)

        user = authenticate(request, username=email, password=password)
        if user is None:
            # Le compte existe peut-être mais n'est pas encore activé : authenticate()
            # renvoie None dans ce cas (ModelBackend rejette les comptes is_active=False).
            existing = User.objects.filter(username=email).first()
            if existing and not existing.is_active and existing.check_password(password):
                return JsonResponse({
                    "success": False,
                    "error": "Votre compte n'est pas encore activé. Vérifiez votre boîte mail (et vos spams) pour le lien d'activation.",
                    "inactive": True,
                }, status=403)
            return JsonResponse({"success": False, "error": "Identifiants invalides"}, status=400)

        login(request, user)
        return JsonResponse({"success": True, "message": "Connecté", "redirect": '/dashboard/'} )

    return render(request, 'login.html')


@require_http_methods(["GET", "POST"])
def forgot_password(request):
    """Demande de réinitialisation : envoie un email avec un lien à usage unique si le
    compte existe. La réponse est identique que l'email existe ou non, pour ne pas
    révéler quelles adresses sont enregistrées sur la plateforme."""
    if request.method == "GET":
        return render(request, 'forgot_password.html')

    email = (request.POST.get("email") or "").strip()
    if not email:
        return JsonResponse({"success": False, "error": "Veuillez saisir votre adresse email."}, status=400)

    generic_message = "Si un compte existe avec cette adresse, un email de réinitialisation vient d'être envoyé."
    user = User.objects.filter(email__iexact=email).first()

    if user is not None:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_link = settings.SITE_BASE_URL.rstrip('/') + reverse('reset_password_confirm', kwargs={'uidb64': uid, 'token': token})

        hours = settings.PASSWORD_RESET_TIMEOUT // 3600
        subject = "Réinitialisation de votre mot de passe InvoiceApp"
        text_body = (
            f"Bonjour {user.company_name},\n\n"
            f"Nous avons bien reçu une demande de réinitialisation du mot de passe associé "
            f"à votre compte InvoiceApp.\n\n"
            f"Choisissez un nouveau mot de passe via ce lien :\n{reset_link}\n\n"
            f"Ce lien est valable {hours} heures.\n\n"
            f"Si vous n'êtes pas à l'origine de cette demande, aucune action n'est nécessaire : "
            f"votre mot de passe actuel reste inchangé.\n\n"
            f"Cordialement,\nL'équipe InvoiceApp\n"
        )
        try:
            _send_transactional_email(
                subject=subject,
                to_email=email,
                greeting_name=user.company_name,
                intro_html="Nous avons bien reçu une demande de réinitialisation du mot de passe associé "
                            "à votre compte InvoiceApp.",
                cta_label="Choisir un nouveau mot de passe",
                cta_url=reset_link,
                outro_html=f"Ce lien est valable {hours} heures. Si vous n'êtes pas à l'origine de cette demande, "
                           f"aucune action n'est nécessaire : votre mot de passe actuel reste inchangé.",
                text_body=text_body,
            )
        except Exception:
            # On ne révèle jamais un éventuel échec technique à l'utilisateur (évite l'énumération
            # de comptes), mais on ne bloque pas non plus la réponse générique.
            pass

    return JsonResponse({"success": True, "message": generic_message})


@require_http_methods(["GET", "POST"])
def reset_password_confirm(request, uidb64, token):
    """Page atteinte via le lien reçu par email : vérifie le token puis permet de
    définir un nouveau mot de passe."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    token_valid = user is not None and default_token_generator.check_token(user, token)

    if request.method == "GET":
        return render(request, 'reset_password_confirm.html', {'token_valid': token_valid})

    if not token_valid:
        return JsonResponse({"success": False, "error": "Ce lien de réinitialisation est invalide ou a expiré."}, status=400)

    new_password = request.POST.get("new_password")
    confirm_password = request.POST.get("confirm_password")
    if not new_password:
        return JsonResponse({"success": False, "error": "Veuillez saisir un nouveau mot de passe."}, status=400)
    if new_password != confirm_password:
        return JsonResponse({"success": False, "error": "Les mots de passe ne correspondent pas."}, status=400)
    if len(new_password) < 8:
        return JsonResponse({"success": False, "error": "Le mot de passe doit contenir au moins 8 caractères."}, status=400)
    try:
        validate_password(new_password, user=user)
    except ValidationError as e:
        return JsonResponse({"success": False, "error": " ".join(e.messages)}, status=400)

    user.set_password(new_password)
    user.save()
    return JsonResponse({"success": True, "message": "Mot de passe réinitialisé. Vous pouvez maintenant vous connecter."})


@require_http_methods(["GET"])
def activate_account(request, uidb64, token):
    """Lien reçu par email après inscription : active le compte et connecte
    directement l'entreprise si le lien est valide."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])
        login(request, user)
        return redirect('dashboard')

    return render(request, 'activation_invalid.html', {
        'email': user.email if user else '',
    })


@require_http_methods(["POST"])
def resend_activation_email(request):
    """Renvoie un email d'activation. Réponse générique (même si l'email n'existe
    pas ou que le compte est déjà actif) pour ne pas révéler quels comptes existent."""
    email = (request.POST.get("email") or "").strip()
    if not email:
        return JsonResponse({"success": False, "error": "Veuillez saisir votre adresse email."}, status=400)

    generic_message = "Si un compte inactif existe avec cette adresse, un email d'activation vient d'être renvoyé."
    user = User.objects.filter(email__iexact=email, is_active=False).first()
    if user is not None:
        try:
            _send_activation_email(user)
        except Exception:
            pass

    return JsonResponse({"success": True, "message": generic_message})


@require_http_methods(["GET", "POST"])
@login_required
def change_password(request):
    if request.method == "GET":
        return render(request, 'change_password.html')
    
    old_password = request.POST.get("old_password")
    new_password = request.POST.get("new_password")
    confirm_password = request.POST.get("confirm_password")

    if not old_password or not new_password:
        return JsonResponse({"success": False, "error": "old_password et new_password requis"}, status=400)
    if new_password != confirm_password:
        return JsonResponse({"success": False, "error": "Les nouveaux mots de passe ne correspondent pas"}, status=400)
    if not request.user.check_password(old_password):
        return JsonResponse({"success": False, "error": "Mot de passe actuel incorrect"}, status=400)
    try:
        validate_password(new_password, user=request.user)
    except ValidationError as e:
        return JsonResponse({"success": False, "error": " ".join(e.messages)}, status=400)

    user = request.user
    user.set_password(new_password)
    user.save()
    update_session_auth_hash(request, user)
    return JsonResponse({"success": True, "message": "Mot de passe modifié"})


@require_http_methods(["GET", "POST"])
@login_required
def delete_account(request):
    if request.method == "GET":
        return render(request, 'delete_account.html')
    
    password = request.POST.get("password")
    if not password or not request.user.check_password(password):
        return JsonResponse({"success": False, "error": "Mot de passe incorrect"}, status=400)
    
    request.user.delete()
    logout(request)
    return JsonResponse({"success": True, "message": "Compte supprimé"})


@require_http_methods(["GET", "POST"])
def logout_view(request):
    logout(request)
    return redirect('login')