"""
Gestion des types et modes de paiement configures par l'entreprise.
"""
from ._common import *  # noqa: F401,F403


@require_http_methods(["GET"])
@login_required
def list_payment_types(request):
    user = request.user
    payment_types = user.payment_types.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'payment_types': payment_types,
    }
    return render(request, 'payment_type_list.html', context)


@require_http_methods(["GET"])
@login_required
def list_payment_methods(request):
    user = request.user
    payment_methods = user.payment_methods.all()
    payment_types = user.payment_types.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'payment_methods': payment_methods,
        'payment_types': payment_types,
    }
    return render(request, 'payment_method_list.html', context)


@require_http_methods(["POST"])
@login_required
def add_payment_type(request):
    payment_type_id = request.POST.get("payment_type_id")
    name = request.POST.get("name")
    description = request.POST.get("description", "")
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)

    if payment_type_id:
        payment_type = PaymentType.objects.filter(id=payment_type_id, company=request.user).first()
        if not payment_type:
            return JsonResponse({"success": False, "error": "Type de paiement introuvable"}, status=404)
        payment_type.name = name
        payment_type.description = description
        payment_type.save()
    else:
        payment_type = PaymentType.objects.create(company=request.user, name=name, description=description)

    return JsonResponse({"success": True, "payment_type_id": payment_type.id, "message": "Type de paiement enregistré"})


@require_http_methods(["POST"])
@login_required
def delete_payment_type(request):
    payment_type_id = request.POST.get("payment_type_id")
    if not payment_type_id:
        return JsonResponse({"success": False, "error": "payment_type_id requis"}, status=400)
    PaymentType.objects.filter(id=payment_type_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Type de paiement supprimé"})


@require_http_methods(["POST"])
@login_required
def add_payment_method(request):
    payment_method_id = request.POST.get("payment_method_id")
    name = request.POST.get("name")
    payment_type_id = request.POST.get("payment_type_id")
    description = request.POST.get("description", "")
    is_active = request.POST.get("is_active", "true").lower() in ["1", "true", "yes"]
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)

    payment_type = PaymentType.objects.filter(id=payment_type_id, company=request.user).first() if payment_type_id else None

    if payment_method_id:
        method = PaymentMethod.objects.filter(id=payment_method_id, company=request.user).first()
        if not method:
            return JsonResponse({"success": False, "error": "Mode de paiement introuvable"}, status=404)
        method.name = name
        method.payment_type = payment_type
        method.description = description
        method.is_active = is_active
        method.save()
    else:
        method = PaymentMethod.objects.create(
            company=request.user,
            name=name,
            payment_type=payment_type,
            description=description,
            is_active=is_active,
        )

    return JsonResponse({"success": True, "payment_method_id": method.id, "message": "Mode de paiement enregistré"})


@require_http_methods(["POST"])
@login_required
def delete_payment_method(request):
    payment_method_id = request.POST.get("payment_method_id")
    if not payment_method_id:
        return JsonResponse({"success": False, "error": "payment_method_id requis"}, status=400)
    PaymentMethod.objects.filter(id=payment_method_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Mode de paiement supprimé"})
