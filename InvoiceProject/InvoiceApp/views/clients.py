"""
Gestion des clients.
"""
from ._common import *  # noqa: F401,F403


@require_http_methods(["GET"])
@login_required
def list_clients(request):
    user = request.user
    clients = user.clients.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'clients': clients,
    }
    return render(request, 'client_list.html', context)


@require_http_methods(["POST"])
@login_required
def add_client(request):
    client_id = request.POST.get("client_id")
    name = request.POST.get("name")
    shop_name = request.POST.get("shop_name", "")
    email = request.POST.get("email", "")
    phone = request.POST.get("phone", "")
    address = request.POST.get("address", "")
    
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)
    
    if client_id:
        # Édition
        try:
            client = Client.objects.get(id=client_id, company=request.user)
            client.name = name
            client.shop_name = shop_name
            client.email = email
            client.phone = phone
            client.address = address
            client.save()
            return JsonResponse({"success": True, "message": "Client modifié", "client_id": client.id})
        except Client.DoesNotExist:
            return JsonResponse({"success": False, "error": "Client non trouvé"}, status=404)
    else:
        # Création
        client = Client.objects.create(
            company=request.user,
            name=name,
            shop_name=shop_name,
            email=email,
            phone=phone,
            address=address,
        )
        return JsonResponse({"success": True, "message": "Client créé", "client_id": client.id})


@require_http_methods(["POST"])
@login_required
def delete_client(request):
    client_id = request.POST.get("client_id")
    if not client_id:
        return JsonResponse({"success": False, "error": "client_id requis"}, status=400)
    Client.objects.filter(id=client_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Client supprimé"})
