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
            'company_logo_url': user.logo.url if user.logo else None,
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
        user.logo = logo
    user.save()

    return JsonResponse({"success": True, "message": "Informations de l'entreprise mises à jour"})
