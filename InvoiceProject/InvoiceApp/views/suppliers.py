"""
Gestion des fournisseurs et des approvisionnements (achats de stock).
"""
from ._common import *  # noqa: F401,F403


@require_http_methods(["GET"])
@login_required
def list_suppliers(request):
    user = request.user
    suppliers = user.suppliers.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'suppliers': suppliers,
    }
    return render(request, 'supplier_list.html', context)


@require_http_methods(["GET"])
@login_required
def list_supplies(request):
    user = request.user
    supplies = user.supplies.all()
    suppliers = user.suppliers.all()
    products = user.products.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'supplies': supplies,
        'suppliers': suppliers,
        'products': products,
    }
    return render(request, 'supply_list.html', context)


@require_http_methods(["POST"])
@login_required
def add_supplier(request):
    supplier_id = request.POST.get("supplier_id")
    name = request.POST.get("name")
    email = request.POST.get("email", "")
    phone = request.POST.get("phone", "")
    address = request.POST.get("address", "")
    
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)
    
    if supplier_id:
        # Édition
        try:
            supplier = Supplier.objects.get(id=supplier_id, company=request.user)
            supplier.name = name
            supplier.email = email
            supplier.phone = phone
            supplier.address = address
            supplier.save()
            return JsonResponse({"success": True, "message": "Fournisseur modifié", "supplier_id": supplier.id})
        except Supplier.DoesNotExist:
            return JsonResponse({"success": False, "error": "Fournisseur non trouvé"}, status=404)
    else:
        # Création
        supplier = Supplier.objects.create(
            company=request.user,
            name=name,
            email=email,
            phone=phone,
            address=address,
        )
        return JsonResponse({"success": True, "message": "Fournisseur créé", "supplier_id": supplier.id})


@require_http_methods(["POST"])
@login_required
def delete_supplier(request):
    supplier_id = request.POST.get("supplier_id")
    if not supplier_id:
        return JsonResponse({"success": False, "error": "supplier_id requis"}, status=400)
    Supplier.objects.filter(id=supplier_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Fournisseur supprimé"})


@require_http_methods(["POST"])
@login_required
def add_supply(request):
    supply_id = request.POST.get("supply_id")
    supplier_id = request.POST.get("supplier_id")
    supply_items_payload = request.POST.get("supply_items")

    if not supplier_id:
        return JsonResponse({"success": False, "error": "supplier_id requis"}, status=400)

    supplier = Supplier.objects.filter(id=supplier_id, company=request.user).first()
    if not supplier:
        return JsonResponse({"success": False, "error": "Fournisseur introuvable"}, status=404)

    if not supply_items_payload:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    try:
        parsed_items = json.loads(supply_items_payload)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Format des produits invalide"}, status=400)

    if not isinstance(parsed_items, list) or not parsed_items:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    items = []
    for item_data in parsed_items:
        product_id = item_data.get('product_id')
        quantity = item_data.get('quantity')
        unit_price = item_data.get('unit_price')
        if not product_id or not quantity:
            return JsonResponse({"success": False, "error": "Chaque ligne doit contenir un produit et une quantité"}, status=400)

        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "quantity doit être un nombre"}, status=400)

        product = Product.objects.filter(id=product_id, company=request.user).first()
        if not product:
            return JsonResponse({"success": False, "error": "Produit introuvable"}, status=404)

        if unit_price in [None, '', 'null']:
            unit_price = product.price
        else:
            try:
                unit_price = Decimal(str(unit_price))
            except (ValueError, TypeError, InvalidOperation):
                return JsonResponse({"success": False, "error": "unit_price doit être un nombre"}, status=400)

        # La devise suit toujours le produit : pas de choix manuel de devise
        items.append((product, quantity, unit_price, product.currency))

    # Récupère l'approvisionnement existant (édition) sans encore rien modifier
    supply = None
    old_items = []
    if supply_id:
        supply = Supply.objects.filter(id=supply_id, company=request.user).first()
        if not supply:
            return JsonResponse({"success": False, "error": "Approvisionnement introuvable"}, status=404)
        old_items = list(supply.supply_items.select_related('product').all())

    with transaction.atomic():
        if supply:
            # Retire l'effet des anciennes lignes sur le stock avant de les remplacer
            for old_item in old_items:
                old_item.product.refresh_from_db(fields=['stock_quantity'])
                old_item.product.stock_quantity -= old_item.quantity
                old_item.product.save(update_fields=['stock_quantity'])
            supply.supplier = supplier
            supply.supply_items.all().delete()
        else:
            supply = Supply.objects.create(company=request.user, supplier=supplier)

        for product, quantity, unit_price, item_currency in items:
            product.refresh_from_db(fields=['stock_quantity'])
            product.stock_quantity += quantity
            product.save(update_fields=['stock_quantity'])

            SupplyItem.objects.create(
                supply=supply,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                currency=item_currency,
            )

        supply.save()

    return JsonResponse({"success": True, "supply_id": supply.id, "message": "Approvisionnement enregistré"})


@require_http_methods(["POST"])
@login_required
def delete_supply(request):
    supply_id = request.POST.get("supply_id")
    if not supply_id:
        return JsonResponse({"success": False, "error": "supply_id requis"}, status=400)

    with transaction.atomic():
        supply = Supply.objects.filter(id=supply_id, company=request.user).first()
        if not supply:
            return JsonResponse({"success": False, "error": "Approvisionnement introuvable"}, status=404)

        for item in supply.supply_items.select_related('product').all():
            item.product.refresh_from_db(fields=['stock_quantity'])
            item.product.stock_quantity = max(0, item.product.stock_quantity - item.quantity)
            item.product.save(update_fields=['stock_quantity'])

        supply.delete()  # cascade supprime les SupplyItem associées

    return JsonResponse({"success": True, "message": "Approvisionnement supprimé"})
