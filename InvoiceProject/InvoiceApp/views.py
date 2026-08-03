import json
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse

from django import forms
from .models import Agent

from .models import (
    User,
    AgentRole,
    Agent,
    Engine,
    Product,
    Client,
    PaymentType,
    PaymentMethod,
    Supplier,
    Supply,
    Sale,
    SaleItem,
    Invoice,
    
)

def landing(request):
    """Landing page - visible to all visitors"""
    return render(request, 'landing.html')

@require_http_methods(["GET", "POST"])
def register_company(request):
    if request.method == "POST":
        company_name = request.POST.get("company_name")
        email = request.POST.get("email")
        password = request.POST.get("password")
        password_confirm = request.POST.get("password_confirm")
        phone = request.POST.get("phone", "")
        address = request.POST.get("address", "")
        logo = request.FILES.get("logo")

        if not company_name or not email or not password:
            return JsonResponse({"success": False, "error": "company_name, email et password obligatoires"}, status=400)
        if password != password_confirm:
            return JsonResponse({"success": False, "error": "Les mots de passe ne correspondent pas"}, status=400)
        if User.objects.filter(username=email).exists() or User.objects.filter(company_email=email).exists():
            return JsonResponse({"success": False, "error": "Un utilisateur avec cet email existe déjà"}, status=400)

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            company_name=company_name,
            company_email=email,
            phone=phone,
            address=address,
            logo=logo,
        )
        return JsonResponse({"success": True, "message": "Compte créé", "user_id": user.id})

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
            return JsonResponse({"success": False, "error": "Identifiants invalides"}, status=400)

        login(request, user)
        return JsonResponse({"success": True, "message": "Connecté", "redirect": '/dashboard/'} )

    return render(request, 'login.html')

@require_http_methods(["GET"])
@login_required
def dashboard(request):
    user = request.user
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'agents_count': user.agents.count(),
        'agent_roles_count': user.agent_roles.count(),
        'engines_count': user.engines.count(),
        'products_count': user.products.count(),
        'clients_count': user.clients.count(),
        'suppliers_count': user.suppliers.count(),
        'payment_methods_count': user.payment_methods.count(),
        'payment_types_count': user.payment_types.count(),
        'sales_count': user.sales.count(),
        'supplies_count': user.supplies.count(),
        'invoices_count': user.invoices.count(),
    }
    return render(request, 'dashboard.html', context)

@require_http_methods(["GET"])
@login_required
def manage_agent_roles(request):
    user = request.user
    agent_roles = user.agent_roles.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'agent_roles': agent_roles,
    }
    return render(request, 'agent_roles_manage.html', context)

@require_http_methods(["GET"])
@login_required
def list_agents(request):
    user = request.user
    agents = user.agents.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'agents': agents,
    }
    return render(request, 'agent_list.html', context)

@require_http_methods(["GET"])
@login_required
def list_engines(request):
    user = request.user
    engines = user.engines.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'engines': engines,
    }
    return render(request, 'engine_list.html', context)

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

@require_http_methods(["GET"])
@login_required
def list_sales(request):
    user = request.user
    sales = user.sales.all()
    clients = user.clients.all()
    products = user.products.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'sales': sales,
        'clients': clients,
        'products': products,
    }
    return render(request, 'sale_list.html', context)

@require_http_methods(["GET"])
@login_required
def list_invoices(request):
    user = request.user
    invoices = user.invoices.all()
    sales = user.sales.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'invoices': invoices,
        'sales': sales,
    }
    return render(request, 'invoice_list.html', context)

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

# Ajout et suppression des éléments des modèles

@require_http_methods(["POST"])
@login_required
def add_agent_role(request):
    name = request.POST.get("name")
    description = request.POST.get("description", "")
    role_id = request.POST.get("role_id")
    company = request.user.company if hasattr(request.user, 'company') else request.user

    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)

    if role_id:
        role = AgentRole.objects.filter(id=role_id, company=company).first()
        if not role:
            return JsonResponse({"success": False, "error": "Rôle introuvable"}, status=404)
        role.name = name
        role.description = description
        role.save()
        return JsonResponse({"success": True, "message": "Rôle mis à jour"})

    role = AgentRole.objects.create(company=company, name=name, description=description)
    return JsonResponse({"success": True, "role_id": role.id, "message": "Rôle ajouté"})

@require_http_methods(["POST"])
@login_required
def delete_agent_role(request):
    role_id = request.POST.get("role_id")
    company = request.user.company if hasattr(request.user, 'company') else request.user
    if not role_id:
        return JsonResponse({"success": False, "error": "role_id requis"}, status=400)
    deleted, _ = AgentRole.objects.filter(id=role_id, company=company).delete()
    if deleted:
        return JsonResponse({"success": True, "message": "Rôle supprimé"})
    return JsonResponse({"success": False, "error": "Rôle introuvable"}, status=404)

@require_http_methods(["GET", "POST"])
@login_required
@require_http_methods(["POST"])
@login_required
def add_agent(request):
    agent_id = request.POST.get("agent_id")
    name = request.POST.get("name") or request.POST.get("first_name", "") + " " + request.POST.get("last_name", "")
    name = name.strip()
    email = request.POST.get("email", "")
    phone = request.POST.get("phone", "")
    role_id = request.POST.get("role_id")
    
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)
    
    role = AgentRole.objects.filter(id=role_id, company=request.user).first() if role_id else None
    
    if agent_id:
        # Édition
        try:
            agent = Agent.objects.get(id=agent_id, company=request.user)
            agent.name = name
            agent.email = email
            agent.phone = phone
            agent.role = role
            agent.save()
            return JsonResponse({"success": True, "message": "Agent modifié", "agent_id": agent.id})
        except Agent.DoesNotExist:
            return JsonResponse({"success": False, "error": "Agent non trouvé"}, status=404)
    else:
        # Création
        agent = Agent.objects.create(company=request.user, name=name, email=email, phone=phone, role=role)
        return JsonResponse({"success": True, "message": "Agent créé", "agent_id": agent.id})



@require_http_methods(["POST"])
@login_required
def delete_agent(request):
    agent_id = request.POST.get("agent_id")
    if not agent_id:
        return JsonResponse({"success": False, "error": "agent_id requis"}, status=400)
    Agent.objects.filter(id=agent_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Agent supprimé"})

@require_http_methods(["POST"])
@login_required
def add_engine(request):
    engine_id = request.POST.get("engine_id")
    name = request.POST.get("name")
    description = request.POST.get("description", "")
    serial_number = request.POST.get("serial_number", "")
    status = request.POST.get("status", "active")
    company = request.user

    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)

    if engine_id:
        try:
            engine = Engine.objects.get(id=engine_id, company=company)
            engine.name = name
            engine.description = description
            engine.serial_number = serial_number
            engine.status = status
            engine.save()
            return JsonResponse({"success": True, "message": "Engin modifié", "engine_id": engine.id})
        except Engine.DoesNotExist:
            return JsonResponse({"success": False, "error": "Engin introuvable"}, status=404)

    engine = Engine.objects.create(
        company=company,
        name=name,
        description=description,
        serial_number=serial_number,
        status=status,
    )
    return JsonResponse({"success": True, "engine_id": engine.id, "message": "Engin ajouté"})

@require_http_methods(["POST"])
@login_required
def delete_engine(request):
    engine_id = request.POST.get("engine_id")
    if not engine_id:
        return JsonResponse({"success": False, "error": "engine_id requis"}, status=400)
    Engine.objects.filter(id=engine_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Engin supprimé"})

@require_http_methods(["POST"])
@login_required
def add_product(request):
    product_id = request.POST.get("product_id")
    name = request.POST.get("name")
    description = request.POST.get("description", "")
    price = request.POST.get("price")
    currency = request.POST.get("currency", "EUR")
    stock = request.POST.get("stock") or request.POST.get("stock_quantity", 0)
    image = request.FILES.get("image") if hasattr(request, 'FILES') else None

    if not name or price is None:
        return JsonResponse({"success": False, "error": "name et price requis"}, status=400)

    valid_currencies = dict(Product.CURRENCY_CHOICES).keys()
    if currency not in valid_currencies:
        currency = "EUR"

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

@require_http_methods(["POST"])
@login_required
def add_client(request):
    client_id = request.POST.get("client_id")
    name = request.POST.get("name")
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
    product_id = request.POST.get("product_id")
    quantity = request.POST.get("quantity")
    unit_price = request.POST.get("unit_price")
    currency = request.POST.get("currency", "EUR")

    if not supplier_id or not product_id or not quantity or not unit_price:
        return JsonResponse({"success": False, "error": "supplier_id, product_id, quantity et unit_price requis"}, status=400)

    try:
        quantity = int(quantity)
        unit_price = float(unit_price)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "quantity et unit_price doivent être des nombres"}, status=400)

    valid_currencies = dict(Product.CURRENCY_CHOICES).keys()
    if currency not in valid_currencies:
        currency = "EUR"

    supplier = Supplier.objects.filter(id=supplier_id, company=request.user).first()
    product = Product.objects.filter(id=product_id, company=request.user).first()
    if not supplier or not product:
        return JsonResponse({"success": False, "error": "Supplier ou Product introuvable"}, status=404)

    if supply_id:
        supply = Supply.objects.filter(id=supply_id, company=request.user).first()
        if not supply:
            return JsonResponse({"success": False, "error": "Approvisionnement introuvable"}, status=404)
        supply.supplier = supplier
        supply.product = product
        supply.quantity = quantity
        supply.unit_price = unit_price
        supply.currency = currency
        supply.save()
    else:
        supply = Supply.objects.create(
            company=request.user,
            supplier=supplier,
            product=product,
            quantity=quantity,
            unit_price=unit_price,
            currency=currency,
        )
    return JsonResponse({"success": True, "supply_id": supply.id, "message": "Approvisionnement enregistré"})

@require_http_methods(["POST"])
@login_required
def delete_supply(request):
    supply_id = request.POST.get("supply_id")
    if not supply_id:
        return JsonResponse({"success": False, "error": "supply_id requis"}, status=400)
    Supply.objects.filter(id=supply_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Approvisionnement supprimé"})

@require_http_methods(["POST"])
@login_required 
def add_sale(request):
    sale_id = request.POST.get("sale_id")
    client_id = request.POST.get("client_id")
    currency = request.POST.get("currency", "EUR")
    sale_items_payload = request.POST.get("sale_items")

    if not client_id:
        return JsonResponse({"success": False, "error": "client_id requis"}, status=400)

    valid_currencies = dict(Product.CURRENCY_CHOICES).keys()
    if currency not in valid_currencies:
        currency = "EUR"

    client = Client.objects.filter(id=client_id, company=request.user).first()
    if not client:
        return JsonResponse({"success": False, "error": "Client introuvable"}, status=404)

    items = []
    if sale_items_payload:
        try:
            parsed_items = json.loads(sale_items_payload)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Format des produits invalide"}, status=400)

        if not isinstance(parsed_items, list) or not parsed_items:
            return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

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

            items.append((product, quantity, unit_price))
    else:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    if sale_id:
        sale = Sale.objects.filter(id=sale_id, company=request.user).first()
        if not sale:
            return JsonResponse({"success": False, "error": "Vente introuvable"}, status=404)

        old_items = list(sale.sale_items.all())
        for old_item in old_items:
            old_item.product.stock_quantity += old_item.quantity
            old_item.product.save(update_fields=['stock_quantity'])

        sale.client = client
        sale.currency = currency
        sale.save()
        sale.sale_items.all().delete()
    else:
        sale = Sale.objects.create(company=request.user, client=client, currency=currency)

    for product, quantity, unit_price in items:
        if product.stock_quantity < quantity:
            if sale_id:
                for old_item in old_items:
                    old_item.product.stock_quantity += old_item.quantity
                    old_item.product.save(update_fields=['stock_quantity'])
            sale.delete()
            return JsonResponse({"success": False, "error": f"Stock insuffisant pour {product.name}"}, status=400)

        product.stock_quantity -= quantity
        product.save(update_fields=['stock_quantity'])

        SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=quantity,
            unit_price=unit_price,
            currency=currency,
        )

    sale.save()
    return JsonResponse({"success": True, "sale_id": sale.id, "message": "Vente enregistrée"})

@require_http_methods(["POST"])
@login_required
def delete_sale(request):
    sale_id = request.POST.get("sale_id")
    if not sale_id:
        return JsonResponse({"success": False, "error": "sale_id requis"}, status=400)
    Sale.objects.filter(id=sale_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Vente supprimée"})

@require_http_methods(["POST"])
@login_required
def add_invoice(request):
    invoice_id = request.POST.get("invoice_id")
    sale_id = request.POST.get("sale_id")
    invoice_number = request.POST.get("invoice_number")
    due_date = request.POST.get("due_date")
    status = request.POST.get("status", "pending")
    if not sale_id or not invoice_number or not due_date:
        return JsonResponse({"success": False, "error": "sale_id, invoice_number et due_date requis"}, status=400)
    
    sale = Sale.objects.filter(id=sale_id, company=request.user).first()
    if not sale:
        return JsonResponse({"success": False, "error": "Vente introuvable"}, status=404)
    
    if invoice_id:
        invoice = Invoice.objects.filter(id=invoice_id, company=request.user).first()
        if not invoice:
            return JsonResponse({"success": False, "error": "Facture introuvable"}, status=404)
        invoice.sale = sale
        invoice.invoice_number = invoice_number
        invoice.due_date = due_date
        invoice.status = status
        invoice.save()
    else:
        invoice = Invoice.objects.create(
            company=request.user,
            sale=sale,
            invoice_number=invoice_number,
            due_date=due_date,
            status=status,
        )
    return JsonResponse({"success": True, "invoice_id": invoice.id, "message": "Facture enregistrée"})

@require_http_methods(["POST"])
@login_required
def delete_invoice(request):
    invoice_id = request.POST.get("invoice_id")
    if not invoice_id:
        return JsonResponse({"success": False, "error": "invoice_id requis"}, status=400)
    Invoice.objects.filter(id=invoice_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Facture supprimée"}) 

def stock(request):
    products = Product.objects.all()
    return render(request, 'stock.html', {'products': products})

def seller(request):
    products = Product.objects.all()
    return render(request, 'seller.html', {'products': products})

def supplier_list(request):
    suppliers = Supplier.objects.all()
    return render(request, 'supplier_list.html', {'suppliers': suppliers})

def supplie_list(request):
    supplies = Supply.objects.all()
    return render(request, 'supplie_list.html', {'supplies': supplies})

def sale_list(request):
    sales = Sale.objects.all()
    return render(request, 'sale_list.html', {'sales': sales})

def product_list(request):
    products = Product.objects.all()
    return render(request, 'product_list.html', {'products': products})

def payment_type_list(request):
    payment_types = PaymentType.objects.all()
    return render(request, 'payment_type_list.html', {'payment_types': payment_types})

def payment_method_list(request):
    payment_methods = PaymentMethod.objects.all()
    return render(request, 'payment_method_list.html', {'payment_methods': payment_methods})

def agent_list(request):
    agents = Agent.objects.all()
    return render(request, 'agent_list.html', {'agents': agents})

def agent_role_list(request):
    agent_roles = AgentRole.objects.all()
    return render(request, 'agent_role_list.html', {'agent_roles': agent_roles})

def invoice_list(request):
    invoices = Invoice.objects.all()
    return render(request, 'invoice_list.html', {'invoices': invoices})

def supplier_list(request):
    suppliers = Supplier.objects.all()
    return render(request, 'supplier_list.html', {'suppliers': suppliers})

def client_list(request):
    clients = Client.objects.all()
    return render(request, 'client_list.html', {'clients': clients})

def engine_list(request):
    engines = Engine.objects.all()
    return render(request, 'engine_list.html', {'engines': engines})


