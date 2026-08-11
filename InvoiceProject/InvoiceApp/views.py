import json
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.utils import timezone

from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas as pdf_canvas

from django import forms
from .models import Agent

from .models import (
    User,
    CURRENCY_CHOICES,
    AgentRole,
    Agent,
    Engine,
    Product,
    Client,
    PaymentType,
    PaymentMethod,
    Supplier,
    Supply,
    SupplyItem,
    Sale,
    SaleItem,
    Invoice,
    Payment,
    AgentStock,
    StockLoad,
    StockLoadItem,
    StockReturn,
    StockReturnItem,
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
        default_currency = request.POST.get("default_currency", "EUR")
        logo = request.FILES.get("logo")

        if not company_name or not email or not password:
            return JsonResponse({"success": False, "error": "company_name, email et password obligatoires"}, status=400)
        if password != password_confirm:
            return JsonResponse({"success": False, "error": "Les mots de passe ne correspondent pas"}, status=400)
        if User.objects.filter(username=email).exists() or User.objects.filter(company_email=email).exists():
            return JsonResponse({"success": False, "error": "Un utilisateur avec cet email existe déjà"}, status=400)

        valid_currencies = dict(CURRENCY_CHOICES).keys()
        if default_currency not in valid_currencies:
            default_currency = "EUR"

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

@require_http_methods(["GET"])
@login_required
def list_agents(request):
    user = request.user
    agents = user.agents.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'agents': agents,
        'roles': user.agent_roles.all(),
        'engines': user.engines.all(),
        'agent_login_code': user.agent_login_code,
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
    agents = user.agents.all()
    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'sales': sales,
        'clients': clients,
        'products': products,
        'agents': agents,
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
    engine_id = request.POST.get("engine_id")
    pin = request.POST.get("pin", "").strip()

    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)

    if pin:
        if not pin.isdigit() or not (4 <= len(pin) <= 6):
            return JsonResponse({"success": False, "error": "Le PIN doit contenir entre 4 et 6 chiffres"}, status=400)
        # Vérifie qu'aucun autre agent actif de l'entreprise n'utilise déjà ce PIN
        other_agents = Agent.objects.filter(company=request.user, is_active=True)
        if agent_id:
            other_agents = other_agents.exclude(id=agent_id)
        for other in other_agents:
            if other.check_pin(pin):
                return JsonResponse({"success": False, "error": "Ce PIN est déjà utilisé par un autre agent"}, status=400)

    role = AgentRole.objects.filter(id=role_id, company=request.user).first() if role_id else None
    engine = Engine.objects.filter(id=engine_id, company=request.user).first() if engine_id else None

    if agent_id:
        # Édition
        try:
            agent = Agent.objects.get(id=agent_id, company=request.user)
            agent.name = name
            agent.email = email
            agent.phone = phone
            agent.role = role
            agent.engine = engine
            if pin:
                agent.set_pin(pin)
            agent.save()
            return JsonResponse({"success": True, "message": "Agent modifié", "agent_id": agent.id})
        except Agent.DoesNotExist:
            return JsonResponse({"success": False, "error": "Agent non trouvé"}, status=404)
    else:
        # Création
        agent = Agent(company=request.user, name=name, email=email, phone=phone, role=role, engine=engine)
        if pin:
            agent.set_pin(pin)
        agent.save()
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

@require_http_methods(["POST"])
@login_required 
def add_sale(request):
    sale_id = request.POST.get("sale_id")
    client_id = request.POST.get("client_id")
    agent_id = request.POST.get("agent_id")
    sale_items_payload = request.POST.get("sale_items")

    if not client_id:
        return JsonResponse({"success": False, "error": "client_id requis"}, status=400)

    client = Client.objects.filter(id=client_id, company=request.user).first()
    if not client:
        return JsonResponse({"success": False, "error": "Client introuvable"}, status=404)

    agent = None
    if agent_id:
        agent = Agent.objects.filter(id=agent_id, company=request.user).first()
        if not agent:
            return JsonResponse({"success": False, "error": "Agent introuvable"}, status=404)

    if not sale_items_payload:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    try:
        parsed_items = json.loads(sale_items_payload)
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

    # Récupère la vente existante (édition) sans encore rien modifier
    sale = None
    old_items = []
    if sale_id:
        sale = Sale.objects.filter(id=sale_id, company=request.user).first()
        if not sale:
            return JsonResponse({"success": False, "error": "Vente introuvable"}, status=404)
        old_items = list(sale.sale_items.select_related('product').all())

    # Simule le stock disponible (en remettant virtuellement les anciennes quantités
    # si on édite) AVANT de valider — aucune écriture en base à ce stade
    stock_preview = {}
    for old_item in old_items:
        base = stock_preview.get(old_item.product_id, old_item.product.stock_quantity)
        stock_preview[old_item.product_id] = base + old_item.quantity

    for product, quantity, unit_price, item_currency in items:
        available = stock_preview.get(product.id, product.stock_quantity)
        if available < quantity:
            return JsonResponse({
                "success": False,
                "error": f"Stock insuffisant pour {product.name} (disponible : {available})"
            }, status=400)
        stock_preview[product.id] = available - quantity

    # Tout est validé : on applique les changements, tout ou rien
    with transaction.atomic():
        if sale:
            for old_item in old_items:
                old_item.product.stock_quantity += old_item.quantity
                old_item.product.save(update_fields=['stock_quantity'])
            sale.client = client
            sale.agent = agent
            sale.sale_items.all().delete()
        else:
            sale = Sale.objects.create(company=request.user, client=client, agent=agent)

        for product, quantity, unit_price, item_currency in items:
            product.refresh_from_db(fields=['stock_quantity'])
            product.stock_quantity -= quantity
            product.save(update_fields=['stock_quantity'])

            SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                currency=item_currency,
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


@require_http_methods(["POST"])
@login_required
def record_invoice_payment(request):
    """Enregistre un paiement supplémentaire sur une facture à crédit ou partiellement payée."""
    invoice_id = request.POST.get("invoice_id")
    amount_input = request.POST.get("amount")

    invoice = Invoice.objects.filter(id=invoice_id, company=request.user).select_related('sale').first()
    if not invoice:
        return JsonResponse({"success": False, "error": "Facture introuvable"}, status=404)

    if not amount_input:
        return JsonResponse({"success": False, "error": "Montant requis"}, status=400)
    try:
        amount = Decimal(str(amount_input))
    except (InvalidOperation, ValueError):
        return JsonResponse({"success": False, "error": "Montant invalide"}, status=400)

    if amount <= 0:
        return JsonResponse({"success": False, "error": "Le montant doit être supérieur à 0"}, status=400)
    if amount > invoice.balance_due:
        return JsonResponse({
            "success": False,
            "error": f"Le montant dépasse le solde restant ({invoice.formatted_balance_due})"
        }, status=400)

    note = request.POST.get("note", "")

    with transaction.atomic():
        Payment.objects.create(invoice=invoice, amount=amount, note=note)
        invoice.amount_paid += amount
        invoice.refresh_status()
        invoice.save(update_fields=['amount_paid', 'status'])

    return JsonResponse({
        "success": True,
        "message": "Paiement enregistré",
        "status": invoice.status,
        "amount_paid": str(invoice.amount_paid),
        "balance_due": str(invoice.balance_due),
    })


def _render_invoice_pdf(invoice):
    company = invoice.company
    sale = invoice.sale
    client = sale.client
    items = sale.sale_items.select_related('product').all()

    buffer = BytesIO()
    p = pdf_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    INDIGO = colors.HexColor('#6366F1')
    DARK = colors.HexColor('#1A2238')
    GREY = colors.HexColor('#64748B')

    # ── EN-TÊTE : logo + entreprise ──
    top = height - 20 * mm
    logo_drawn = False
    if company.logo and hasattr(company.logo, 'path'):
        try:
            p.drawImage(company.logo.path, 20 * mm, top - 18 * mm, width=22 * mm, height=22 * mm,
                        preserveAspectRatio=True, mask='auto')
            logo_drawn = True
        except Exception:
            logo_drawn = False

    text_x = 46 * mm if logo_drawn else 20 * mm
    p.setFillColor(DARK)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(text_x, top - 4 * mm, company.company_name)
    p.setFillColor(GREY)
    p.setFont("Helvetica", 9)
    if company.address:
        p.drawString(text_x, top - 10 * mm, company.address[:60])
    if company.phone or company.company_email:
        p.drawString(text_x, top - 15 * mm, f"{company.phone}  {company.company_email or ''}".strip())

    p.setFillColor(INDIGO)
    p.setFont("Helvetica-Bold", 22)
    p.drawRightString(width - 20 * mm, top - 4 * mm, "FACTURE")
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 11)
    p.drawRightString(width - 20 * mm, top - 12 * mm, invoice.invoice_number)
    p.setFont("Helvetica", 9)
    p.setFillColor(GREY)
    p.drawRightString(width - 20 * mm, top - 17 * mm, f"Émise le {invoice.issued_date.strftime('%d/%m/%Y')}")
    p.drawRightString(width - 20 * mm, top - 22 * mm, f"Échéance : {invoice.due_date.strftime('%d/%m/%Y')}")

    status_labels = dict(Invoice._meta.get_field('status').choices)
    status_colors = {
        'paid': colors.HexColor('#10B981'),
        'pending': colors.HexColor('#F59E0B'),
        'partial': colors.HexColor('#38BDF8'),
        'overdue': colors.HexColor('#F43F5E'),
    }
    p.setFillColor(status_colors.get(invoice.status, colors.grey))
    p.setFont("Helvetica-Bold", 9)
    p.drawRightString(width - 20 * mm, top - 28 * mm, status_labels.get(invoice.status, invoice.status).upper())

    p.setStrokeColor(colors.HexColor('#E2E8F0'))
    p.line(20 * mm, top - 34 * mm, width - 20 * mm, top - 34 * mm)

    # ── BLOC CLIENT ──
    client_top = top - 44 * mm
    p.setFillColor(GREY)
    p.setFont("Helvetica-Bold", 9)
    p.drawString(20 * mm, client_top, "FACTURÉ À")
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 12)
    display_name = client.shop_name or client.name
    p.drawString(20 * mm, client_top - 7 * mm, display_name)
    p.setFont("Helvetica", 9.5)
    p.setFillColor(GREY)
    line_y = client_top - 13 * mm
    if client.shop_name:
        p.drawString(20 * mm, line_y, f"Contact : {client.name}")
        line_y -= 5 * mm
    if client.phone:
        p.drawString(20 * mm, line_y, client.phone)
        line_y -= 5 * mm
    if client.address:
        p.drawString(20 * mm, line_y, client.address[:70])

    agent_name = sale.agent.name if sale.agent else None
    if agent_name:
        p.setFillColor(GREY)
        p.setFont("Helvetica", 9)
        p.drawRightString(width - 20 * mm, client_top, f"Vendeur : {agent_name}")

    # ── TABLEAU DES PRODUITS ──
    table_top = client_top - 30 * mm
    p.setFillColor(DARK)
    p.rect(20 * mm, table_top - 7 * mm, width - 40 * mm, 7 * mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 9)
    p.drawString(23 * mm, table_top - 5 * mm, "Produit")
    p.drawCentredString(125 * mm, table_top - 5 * mm, "Qté")
    p.drawRightString(160 * mm, table_top - 5 * mm, "Prix unitaire")
    p.drawRightString(width - 23 * mm, table_top - 5 * mm, "Total")

    row_y = table_top - 15 * mm
    p.setFont("Helvetica", 9.5)
    for i, item in enumerate(items):
        if row_y < 30 * mm:
            p.showPage()
            row_y = height - 20 * mm
        bg = colors.HexColor('#F8FAFC') if i % 2 == 0 else colors.white
        p.setFillColor(bg)
        p.rect(20 * mm, row_y - 4 * mm, width - 40 * mm, 8 * mm, fill=1, stroke=0)
        p.setFillColor(colors.black)
        p.drawString(23 * mm, row_y, item.product.name[:48])
        p.drawCentredString(125 * mm, row_y, str(item.quantity))
        symbols = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}
        symbol = symbols.get(item.currency, item.currency)
        p.drawRightString(160 * mm, row_y, f"{item.unit_price:,.2f} {symbol}")
        p.drawRightString(width - 23 * mm, row_y, f"{item.total_price:,.2f} {symbol}")
        row_y -= 8 * mm

    row_y -= 4 * mm
    p.setStrokeColor(colors.HexColor('#E2E8F0'))
    p.line(120 * mm, row_y, width - 20 * mm, row_y)
    row_y -= 9 * mm
    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(INDIGO)
    p.drawRightString(width - 23 * mm, row_y, f"Total : {sale.formatted_total_price}")

    if invoice.status != 'paid':
        row_y -= 7 * mm
        p.setFont("Helvetica", 9.5)
        p.setFillColor(colors.HexColor('#10B981'))
        p.drawRightString(width - 23 * mm, row_y, f"Déjà payé : {invoice.formatted_amount_paid}")
        row_y -= 6 * mm
        p.setFillColor(colors.HexColor('#F43F5E'))
        p.setFont("Helvetica-Bold", 10.5)
        p.drawRightString(width - 23 * mm, row_y, f"Reste à payer : {invoice.formatted_balance_due}")

    p.setFillColor(GREY)
    p.setFont("Helvetica-Oblique", 8)
    p.drawCentredString(width / 2, 15 * mm, "Merci de votre confiance.")
    p.setFont("Helvetica", 7)
    p.drawCentredString(width / 2, 10 * mm, f"{company.company_name} — Facture générée automatiquement, numéro unique {invoice.invoice_number}")

    p.showPage()
    p.save()
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'
    return response


@require_http_methods(["GET"])
@login_required
def invoice_pdf(request, invoice_id):
    invoice = Invoice.objects.filter(id=invoice_id, company=request.user).select_related(
        'sale', 'sale__client', 'company'
    ).first()
    if not invoice:
        return HttpResponse("Facture introuvable", status=404)
    return _render_invoice_pdf(invoice)


# ══════════════════════════════════════════════════════════════════
#  ESPACE VENDEUR (agents) — authentification par code entreprise + PIN
#  Complètement séparé de la session admin (request.user).
#  L'agent connecté est accessible via request.agent dans les vues ci-dessous.
# ══════════════════════════════════════════════════════════════════

def generate_invoice_number(company):
    """Génère un numéro de facture séquentiel et unique par entreprise, sans collision
    même en cas de ventes simultanées (verrouillage de la ligne de l'entreprise)."""
    with transaction.atomic():
        locked_company = User.objects.select_for_update().get(pk=company.pk)
        number = locked_company.next_invoice_number
        locked_company.next_invoice_number = number + 1
        locked_company.save(update_fields=['next_invoice_number'])
    year = timezone.now().year
    return f"FAC-{year}-{number:05d}"


def agent_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        agent_id = request.session.get('agent_id')
        if not agent_id:
            return redirect('vendor_login')
        agent = Agent.objects.filter(id=agent_id, is_active=True).select_related('company', 'role').first()
        if not agent:
            request.session.flush()
            return redirect('vendor_login')
        request.agent = agent
        return view_func(request, *args, **kwargs)
    return wrapper


@require_http_methods(["GET", "POST"])
def vendor_login(request):
    if request.method == "GET":
        return render(request, 'vendor_login.html')

    company_code = request.POST.get("company_code", "").strip().upper()
    pin = request.POST.get("pin", "").strip()

    if not company_code or not pin:
        return JsonResponse({"success": False, "error": "Code entreprise et PIN requis"}, status=400)

    company = User.objects.filter(agent_login_code=company_code).first()
    if not company:
        return JsonResponse({"success": False, "error": "Code entreprise invalide"}, status=400)

    matched_agent = None
    for agent in Agent.objects.filter(company=company, is_active=True):
        if agent.check_pin(pin):
            matched_agent = agent
            break

    if not matched_agent:
        return JsonResponse({"success": False, "error": "PIN invalide"}, status=400)

    request.session['agent_id'] = matched_agent.id
    return JsonResponse({"success": True, "message": "Connecté", "redirect": "/vendeur/"})


@require_http_methods(["GET", "POST"])
def vendor_logout(request):
    request.session.flush()
    return redirect('vendor_login')


@require_http_methods(["GET"])
@agent_login_required
def vendor_invoice_pdf(request, invoice_id):
    invoice = Invoice.objects.filter(id=invoice_id, company=request.agent.company).select_related(
        'sale', 'sale__client', 'company'
    ).first()
    if not invoice:
        return HttpResponse("Facture introuvable", status=404)
    return _render_invoice_pdf(invoice)


@agent_login_required
def vendor_dashboard(request):
    agent = request.agent
    agent_stocks = AgentStock.objects.filter(agent=agent, quantity__gt=0).select_related('product').order_by('product__name')
    clients = Client.objects.filter(company=agent.company)
    recent_sales = Sale.objects.filter(company=agent.company, agent=agent).select_related('invoice', 'client').order_by('-date')[:15]
    context = {
        'agent': agent,
        'company_name': agent.company.company_name,
        'company_logo_url': agent.company.logo.url if agent.company.logo else None,
        'agent_stocks': agent_stocks,
        'clients': clients,
        'sales': recent_sales,
    }
    return render(request, 'vendor_dashboard.html', context)


@require_http_methods(["POST"])
@agent_login_required
def vendor_add_sale(request):
    agent = request.agent
    company = agent.company

    client_id = request.POST.get("client_id")
    new_client_name = request.POST.get("new_client_name", "").strip()
    new_client_shop_name = request.POST.get("new_client_shop_name", "").strip()
    new_client_phone = request.POST.get("new_client_phone", "").strip()
    sale_items_payload = request.POST.get("sale_items")
    payment_type = request.POST.get("payment_type", "full")  # full | credit | partial
    amount_paid_input = request.POST.get("amount_paid", "")
    due_date_input = request.POST.get("due_date", "")

    if payment_type not in ("full", "credit", "partial"):
        payment_type = "full"

    # Client existant OU création rapide d'un nouveau client
    if client_id:
        client = Client.objects.filter(id=client_id, company=company).first()
        if not client:
            return JsonResponse({"success": False, "error": "Client introuvable"}, status=404)
    elif new_client_name:
        client = Client.objects.create(company=company, name=new_client_name, shop_name=new_client_shop_name, phone=new_client_phone)
    else:
        return JsonResponse({"success": False, "error": "Sélectionnez un client ou renseignez son nom"}, status=400)

    if not sale_items_payload:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)
    try:
        parsed_items = json.loads(sale_items_payload)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Format des produits invalide"}, status=400)
    if not isinstance(parsed_items, list) or not parsed_items:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    items = []
    for item_data in parsed_items:
        product_id = item_data.get('product_id')
        quantity = item_data.get('quantity')
        if not product_id or not quantity:
            return JsonResponse({"success": False, "error": "Chaque ligne doit contenir un produit et une quantité"}, status=400)
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "quantity doit être un nombre"}, status=400)

        # Sécurité : le prix vient TOUJOURS du stock personnel du vendeur (fixé par la secrétaire
        # au moment du chargement), jamais de ce que le vendeur envoie, et jamais du prix catalogue.
        agent_stock = AgentStock.objects.filter(agent=agent, product_id=product_id).select_related('product').first()
        if not agent_stock:
            return JsonResponse({"success": False, "error": "Ce produit n'est pas dans ton stock"}, status=404)

        items.append((agent_stock, quantity))

    # Validation du stock PERSONNEL du vendeur avant toute écriture
    stock_preview = {}
    for agent_stock, quantity in items:
        available = stock_preview.get(agent_stock.product_id, agent_stock.quantity)
        if available < quantity:
            return JsonResponse({
                "success": False,
                "error": f"Stock insuffisant pour {agent_stock.product.name} (disponible chez toi : {available})"
            }, status=400)
        stock_preview[agent_stock.product_id] = available - quantity

    sale_total = sum((agent_stock.unit_price * quantity for agent_stock, quantity in items), Decimal('0.00'))

    # Validation du paiement (comptant / crédit / avance) avant toute écriture
    today = timezone.now().date()
    if payment_type == "full":
        amount_paid = sale_total
        due_date = today
    elif payment_type == "credit":
        amount_paid = Decimal('0.00')
        if not due_date_input:
            return JsonResponse({"success": False, "error": "Indique une date d'échéance pour le crédit"}, status=400)
        try:
            due_date = timezone.datetime.strptime(due_date_input, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"success": False, "error": "Date d'échéance invalide"}, status=400)
    else:  # partial
        if not amount_paid_input:
            return JsonResponse({"success": False, "error": "Indique le montant déjà versé"}, status=400)
        try:
            amount_paid = Decimal(str(amount_paid_input))
        except (InvalidOperation, ValueError):
            return JsonResponse({"success": False, "error": "Montant versé invalide"}, status=400)
        if amount_paid <= 0 or amount_paid >= sale_total:
            return JsonResponse({"success": False, "error": "Le montant versé doit être supérieur à 0 et inférieur au total (sinon utilise « payé en totalité »)"}, status=400)
        if not due_date_input:
            return JsonResponse({"success": False, "error": "Indique une date d'échéance pour le solde restant"}, status=400)
        try:
            due_date = timezone.datetime.strptime(due_date_input, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"success": False, "error": "Date d'échéance invalide"}, status=400)

    with transaction.atomic():
        sale = Sale.objects.create(company=company, client=client, agent=agent)

        for agent_stock, quantity in items:
            agent_stock.refresh_from_db(fields=['quantity'])
            agent_stock.quantity -= quantity
            agent_stock.save(update_fields=['quantity'])

            SaleItem.objects.create(
                sale=sale,
                product=agent_stock.product,
                quantity=quantity,
                unit_price=agent_stock.unit_price,
                currency=agent_stock.currency,
            )

        sale.save()

        # Facture générée automatiquement, une seule fois, numéro garanti unique et séquentiel
        invoice_number = generate_invoice_number(company)
        invoice = Invoice.objects.create(
            company=company,
            sale=sale,
            invoice_number=invoice_number,
            due_date=due_date,
            amount_paid=amount_paid,
        )
        invoice.refresh_status()
        invoice.save(update_fields=['status'])

        if amount_paid > 0:
            Payment.objects.create(
                invoice=invoice, amount=amount_paid, recorded_by_agent=agent,
                note="Versement à la vente" if payment_type == "partial" else "Paiement comptant"
            )


    return JsonResponse({
        "success": True,
        "message": "Vente enregistrée",
        "sale_id": sale.id,
        "invoice_number": invoice.invoice_number,
        "invoice_id": invoice.id,
    }) 


@require_http_methods(["POST"])
@agent_login_required
def vendor_add_payment(request):
    """Le vendeur enregistre un versement complémentaire sur une vente à crédit/avance qu'il a faite."""
    agent = request.agent
    invoice_id = request.POST.get("invoice_id")
    amount_input = request.POST.get("amount")

    invoice = Invoice.objects.filter(id=invoice_id, company=agent.company, sale__agent=agent).select_related('sale').first()
    if not invoice:
        return JsonResponse({"success": False, "error": "Facture introuvable"}, status=404)

    if not amount_input:
        return JsonResponse({"success": False, "error": "Montant requis"}, status=400)
    try:
        amount = Decimal(str(amount_input))
    except (InvalidOperation, ValueError):
        return JsonResponse({"success": False, "error": "Montant invalide"}, status=400)

    if amount <= 0:
        return JsonResponse({"success": False, "error": "Le montant doit être supérieur à 0"}, status=400)
    if amount > invoice.balance_due:
        return JsonResponse({
            "success": False,
            "error": f"Le montant dépasse le solde restant ({invoice.formatted_balance_due})"
        }, status=400)

    with transaction.atomic():
        Payment.objects.create(invoice=invoice, amount=amount, recorded_by_agent=agent, note="Versement enregistré par le vendeur")
        invoice.amount_paid += amount
        invoice.refresh_status()
        invoice.save(update_fields=['amount_paid', 'status'])

    return JsonResponse({
        "success": True,
        "message": "Paiement enregistré",
        "status": invoice.status,
        "balance_due": str(invoice.balance_due),
    })


# ═══════════════════════════════════════════════════════════════
# Gestion du stock vendeur (chargement / retour de tournée) — ADMIN
# ═══════════════════════════════════════════════════════════════

@require_http_methods(["GET"])
@login_required
def list_stock_loads(request):
    user = request.user
    agents = user.agents.all()
    engines = user.engines.all()
    products = user.products.all()
    agent_stocks = AgentStock.objects.filter(agent__company=user).select_related('agent', 'product').filter(quantity__gt=0).order_by('agent__name', 'product__name')
    loads = StockLoad.objects.filter(company=user).select_related('agent', 'engine').prefetch_related('items__product').order_by('-date')[:30]
    returns = StockReturn.objects.filter(company=user).select_related('agent').prefetch_related('items__product').order_by('-date')[:30]

    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'agents': agents,
        'engines': engines,
        'products': products,
        'agent_stocks': agent_stocks,
        'loads': loads,
        'returns': returns,
    }
    return render(request, 'stock_loads.html', context)


@require_http_methods(["POST"])
@login_required
def add_stock_load(request):
    user = request.user
    agent_id = request.POST.get("agent_id")
    engine_id = request.POST.get("engine_id")
    note = request.POST.get("note", "")
    items_payload = request.POST.get("items")

    agent = Agent.objects.filter(id=agent_id, company=user).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent introuvable"}, status=404)

    # Engin utilisé pour cette tournée : celui choisi explicitement, sinon l'engin par défaut de l'agent
    engine = None
    if engine_id:
        engine = Engine.objects.filter(id=engine_id, company=user).first()
        if not engine:
            return JsonResponse({"success": False, "error": "Engin introuvable"}, status=404)
    else:
        engine = agent.engine

    if not items_payload:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)
    try:
        parsed_items = json.loads(items_payload)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Format des produits invalide"}, status=400)
    if not isinstance(parsed_items, list) or not parsed_items:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    items = []
    for item_data in parsed_items:
        product_id = item_data.get('product_id')
        quantity = item_data.get('quantity')
        unit_price = item_data.get('unit_price')
        if not product_id or not quantity or unit_price in [None, '']:
            return JsonResponse({"success": False, "error": "Chaque ligne doit contenir un produit, une quantité et un prix"}, status=400)
        try:
            quantity = int(quantity)
            unit_price = Decimal(str(unit_price))
        except (ValueError, TypeError, InvalidOperation):
            return JsonResponse({"success": False, "error": "quantity et unit_price doivent être des nombres"}, status=400)

        product = Product.objects.filter(id=product_id, company=user).first()
        if not product:
            return JsonResponse({"success": False, "error": "Produit introuvable"}, status=404)

        items.append((product, quantity, unit_price))

    # Validation du stock MAGASIN avant toute écriture (on ne peut pas charger plus que ce qu'il y a)
    stock_preview = {}
    for product, quantity, unit_price in items:
        available = stock_preview.get(product.id, product.stock_quantity)
        if available < quantity:
            return JsonResponse({
                "success": False,
                "error": f"Stock magasin insuffisant pour {product.name} (disponible : {available})"
            }, status=400)
        stock_preview[product.id] = available - quantity

    with transaction.atomic():
        load = StockLoad.objects.create(company=user, agent=agent, engine=engine, note=note)

        for product, quantity, unit_price in items:
            product.refresh_from_db(fields=['stock_quantity'])
            product.stock_quantity -= quantity
            product.save(update_fields=['stock_quantity'])

            StockLoadItem.objects.create(
                load=load, product=product, quantity=quantity,
                unit_price=unit_price, currency=product.currency,
            )

            agent_stock, _ = AgentStock.objects.get_or_create(
                agent=agent, product=product,
                defaults={'quantity': 0, 'unit_price': unit_price, 'currency': product.currency}
            )
            agent_stock.quantity += quantity
            agent_stock.unit_price = unit_price
            agent_stock.currency = product.currency
            agent_stock.save()

    return JsonResponse({"success": True, "message": f"Chargement enregistré pour {agent.name}"})


@require_http_methods(["POST"])
@login_required
def add_stock_return(request):
    user = request.user
    agent_id = request.POST.get("agent_id")
    note = request.POST.get("note", "")
    items_payload = request.POST.get("items")

    agent = Agent.objects.filter(id=agent_id, company=user).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent introuvable"}, status=404)

    if not items_payload:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)
    try:
        parsed_items = json.loads(items_payload)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Format des produits invalide"}, status=400)
    if not isinstance(parsed_items, list) or not parsed_items:
        return JsonResponse({"success": False, "error": "Au moins un produit est requis"}, status=400)

    items = []
    for item_data in parsed_items:
        product_id = item_data.get('product_id')
        quantity = item_data.get('quantity')
        if not product_id or not quantity:
            return JsonResponse({"success": False, "error": "Chaque ligne doit contenir un produit et une quantité"}, status=400)
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "quantity doit être un nombre"}, status=400)

        agent_stock = AgentStock.objects.filter(agent=agent, product_id=product_id).select_related('product').first()
        if not agent_stock:
            return JsonResponse({"success": False, "error": "Ce vendeur n'a pas ce produit en stock"}, status=404)

        items.append((agent_stock, quantity))

    # Validation du stock VENDEUR avant toute écriture (on ne peut pas retourner plus que ce qu'il a)
    stock_preview = {}
    for agent_stock, quantity in items:
        available = stock_preview.get(agent_stock.product_id, agent_stock.quantity)
        if available < quantity:
            return JsonResponse({
                "success": False,
                "error": f"{agent.name} n'a que {available} de {agent_stock.product.name} — impossible de retourner {quantity}"
            }, status=400)
        stock_preview[agent_stock.product_id] = available - quantity

    with transaction.atomic():
        stock_return = StockReturn.objects.create(company=user, agent=agent, note=note)

        for agent_stock, quantity in items:
            agent_stock.refresh_from_db(fields=['quantity'])
            agent_stock.quantity -= quantity
            agent_stock.save(update_fields=['quantity'])

            StockReturnItem.objects.create(stock_return=stock_return, product=agent_stock.product, quantity=quantity)

            product = agent_stock.product
            product.refresh_from_db(fields=['stock_quantity'])
            product.stock_quantity += quantity
            product.save(update_fields=['stock_quantity'])

    return JsonResponse({"success": True, "message": f"Retour enregistré pour {agent.name}"})