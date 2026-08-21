"""
Gestion du catalogue produits.
"""
from ._common import *  # noqa: F401,F403


@require_http_methods(["GET"])
@login_required
def list_products(request):
    user = request.user
    products = user.products.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'products': products,
    }
    return render(request, 'product_list.html', context)


@require_http_methods(["POST"])
@login_required
def add_product(request):
    product_id = request.POST.get("product_id")
    name = request.POST.get("name")
    description = request.POST.get("description", "")
    price = request.POST.get("price")
    stock = request.POST.get("stock") or request.POST.get("stock_quantity", 0)
    image = request.FILES.get("image") if hasattr(request, 'FILES') else None

    if not name or price is None:
        return JsonResponse({"success": False, "error": "name et price requis"}, status=400)

    # La devise est celle de l'entreprise, définie une fois à l'inscription :
    # inutile de la redemander à chaque produit
    currency = request.user.default_currency

    stock_quantity = int(stock) if stock not in (None, "", "0") else 0

    if product_id:
        try:
            product = Product.objects.get(id=product_id, company=request.user)
            product.name = name
            product.description = description
            product.price = price
            product.currency = currency
            product.stock_quantity = stock_quantity
            if image:
                product.image = image
            product.save()
            return JsonResponse({"success": True, "message": "Produit modifié", "product_id": product.id})
        except Product.DoesNotExist:
            return JsonResponse({"success": False, "error": "Produit non trouvé"}, status=404)
    else:
        product = Product.objects.create(
            company=request.user,
            name=name,
            description=description,
            price=price,
            currency=currency,
            stock_quantity=stock_quantity,
            image=image,
        )
        return JsonResponse({"success": True, "message": "Produit créé", "product_id": product.id})


@require_http_methods(["POST"])
@login_required
def delete_product(request):
    product_id = request.POST.get("product_id")
    if not product_id:
        return JsonResponse({"success": False, "error": "product_id requis"}, status=400)
    Product.objects.filter(id=product_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Produit supprimé"})
