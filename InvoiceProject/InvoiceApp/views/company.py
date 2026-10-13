"""
Parametres de l'entreprise connectee.
"""
from ._common import *  # noqa: F401,F403


@require_http_methods(["GET", "POST"])
@login_required
def company_settings(request):
    user = request.user

    if request.method == "GET":
        context = {
            'company_name': user.company_name,
            'company_logo_url': user.logo_url,
        }
        return render(request, 'company_settings.html', context)

    company_name = request.POST.get("company_name")
    company_email = request.POST.get("company_email", "")
    phone = request.POST.get("phone", "")
    address = request.POST.get("address", "")
    default_currency = request.POST.get("default_currency", user.default_currency)
    logo = request.FILES.get("logo")

    if not company_name:
        return JsonResponse({"success": False, "error": "company_name requis"}, status=400)

    if company_email and User.objects.filter(company_email=company_email).exclude(id=user.id).exists():
        return JsonResponse({"success": False, "error": "Cet email est déjà utilisé par une autre entreprise"}, status=400)

    valid_currencies = dict(CURRENCY_CHOICES).keys()
    if default_currency not in valid_currencies:
        default_currency = user.default_currency

    user.company_name = company_name
    user.company_email = company_email
    user.phone = phone
    user.address = address
    user.default_currency = default_currency
    if logo:
        # Validation taille et extension
        if logo.size > 2 * 1024 * 1024:
            return JsonResponse({"success": False, "error": "Le fichier du logo est trop volumineux (maximum 2 Mo)."}, status=400)
        allowed_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.svg')
        if not any(logo.name.lower().endswith(ext) for ext in allowed_extensions):
            return JsonResponse({"success": False, "error": "Format d'image non supporté. Formats acceptés : PNG, JPG, JPEG, WEBP, SVG."}, status=400)
        user.logo = logo

    try:
        user.save()
    except Exception as e:
        logger.exception("Erreur lors de l'enregistrement de l'entreprise ou du logo: %s", e)
        err_lower = str(e).lower()
        if any(k in err_lower for k in ("accessdenied", "invalidaccesskey", "signaturedoesnotmatch")):
            msg = "Erreur de stockage distant (Cloudflare R2) : identifiants S3 invalides ou permissions insuffisantes (Object Read & Write requis)."
        elif "nosuchbucket" in err_lower:
            msg = "Erreur de stockage distant (Cloudflare R2) : le bucket spécifié est introuvable."
        elif any(k in err_lower for k in ("ssl", "endpoint", "connection", "nodename")):
            msg = "Erreur de connexion au stockage distant (Cloudflare R2) : impossible de joindre le serveur. Vérifiez l'Account ID et l'endpoint."
        else:
            msg = f"Erreur lors de l'enregistrement : {str(e)}"
        return JsonResponse({"success": False, "error": msg}, status=400)

    return JsonResponse({"success": True, "message": "Informations de l'entreprise mises à jour"})
