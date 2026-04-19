from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse

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
    Invoice,
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

@require_http_methods(["POST"])
@login_required
def change_password(request):
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

@require_http_methods(["POST"])
@login_required
def delete_account(request):
    request.user.delete()
    logout(request)
    return JsonResponse({"success": True, "message": "Compte supprimé"})

# Ajout et suppression des éléments des modèles

@require_http_methods(["POST"])
@login_required
def add_agent_role(request):
    name = request.POST.get("name")
    description = request.POST.get("description", "")
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)
    role = AgentRole.objects.create(company=request.user, name=name, description=description)
    return JsonResponse({"success": True, "role_id": role.id})

@require_http_methods(["POST"])
@login_required
def delete_agent_role(request):
    role_id = request.POST.get("role_id")
    if not role_id:
        return JsonResponse({"success": False, "error": "role_id requis"}, status=400)
    AgentRole.objects.filter(id=role_id, company=request.user).delete()
    return JsonResponse({"success": True, "message": "Rôle supprimé"})

@require_http_methods(["POST"])
@login_required
def add_agent(request):
    name = request.POST.get("name")
    email = request.POST.get("email", "")
    phone = request.POST.get("phone", "")
    role_id = request.POST.get("role_id")
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)
    role = AgentRole.objects.filter(id=role_id).first() if role_id else None
    agent = Agent.objects.create(company=request.user, name=name, email=email, phone=phone, role=role)
    return JsonResponse({"success": True, "agent_id": agent.id})

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
    name = request.POST.get("name")
    description = request.POST.get("description", "")
    serial_number = request.POST.get("serial_number", "")
    status = request.POST.get("status", "active")
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)
    engine = Engine.objects.create(
        company=request.user,
        name=name,
        description=description,
        serial_number=serial_number,
        status=status,
    )
    return JsonResponse({"success": True, "engine_id": engine.id})

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
    name = request.POST.get("name")
    description = request.POST.get("description", "")
    price = request.POST.get("price")
    stock_quantity = request.POST.get("stock_quantity", 0)
    image = request.FILES.get("image") if hasattr(request, 'FILES') else None
    if not name or price is None:
        return JsonResponse({"success": False, "error": "name et price requis"}, status=400)
    product = Product.objects.create(
        company=request.user,
        name=name,
        description=description,
        price=price,
        stock_quantity=stock_quantity,
        image=image,
    )
    return JsonResponse({"success": True, "product_id": product.id})

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
    name = request.POST.get("name")
    email = request.POST.get("email", "")
    phone = request.POST.get("phone", "")
    address = request.POST.get("address", "")
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)
    client = Client.objects.create(
        company=request.user,
        name=name,
        email=email,
        phone=phone,
        address=address,
    )
    return JsonResponse({"success": True, "client_id": client.id})

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
    name = request.POST.get("name")
    description = request.POST.get("description", "")
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)
    payment_type = PaymentType.objects.create(company=request.user, name=name, description=description)
    return JsonResponse({"success": True, "payment_type_id": payment_type.id})

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
    name = request.POST.get("name")
    payment_type_id = request.POST.get("payment_type_id")
    description = request.POST.get("description", "")
    is_active = request.POST.get("is_active", "true").lower() in ["1", "true", "yes"]
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)
    payment_type = PaymentType.objects.filter(id=payment_type_id).first() if payment_type_id else None
    method = PaymentMethod.objects.create(
        company=request.user,
        name=name,
        payment_type=payment_type,
        description=description,
        is_active=is_active,
    )
    return JsonResponse({"success": True, "payment_method_id": method.id})

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
    name = request.POST.get("name")
    email = request.POST.get("email", "")
    phone = request.POST.get("phone", "")
    address = request.POST.get("address", "")
    if not name:
        return JsonResponse({"success": False, "error": "name requis"}, status=400)
    supplier = Supplier.objects.create(
        company=request.user,
        name=name,
        email=email,
        phone=phone,
        address=address,
    )
    return JsonResponse({"success": True, "supplier_id": supplier.id})

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
    supplier_id = request.POST.get("supplier_id")
    product_id = request.POST.get("product_id")
    quantity = request.POST.get("quantity")
    unit_price = request.POST.get("unit_price")
    if not supplier_id or not product_id or not quantity or not unit_price:
        return JsonResponse({"success": False, "error": "supplier_id, product_id, quantity et unit_price requis"}, status=400)
    supplier = Supplier.objects.filter(id=supplier_id, company=request.user).first()
    product = Product.objects.filter(id=product_id, company=request.user).first()
    if not supplier or not product:
        return JsonResponse({"success": False, "error": "Supplier ou Product introuvable"}, status=404)
    supply = Supply.objects.create(
        company=request.user,
        supplier=supplier,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
    )
    return JsonResponse({"success": True, "supply_id": supply.id})

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
    client_id = request.POST.get("client_id")
    product_id = request.POST.get("product_id")
    quantity = request.POST.get("quantity")
    unit_price = request.POST.get("unit_price")
    if not client_id or not product_id or not quantity or not unit_price:
        return JsonResponse({"success": False, "error": "client_id, product_id, quantity et unit_price requis"}, status=400)
    client = Client.objects.filter(id=client_id, company=request.user).first()
    product = Product.objects.filter(id=product_id, company=request.user).first()
    if not client or not product:
        return JsonResponse({"success": False, "error": "Client ou Produit introuvable"}, status=404)
    sale = Sale.objects.create(
        company=request.user,
        client=client,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
    )
    return JsonResponse({"success": True, "sale_id": sale.id})

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
    sale_id = request.POST.get("sale_id")
    invoice_number = request.POST.get("invoice_number")
    due_date = request.POST.get("due_date")
    status = request.POST.get("status", "pending")
    if not sale_id or not invoice_number or not due_date:
        return JsonResponse({"success": False, "error": "sale_id, invoice_number et due_date requis"}, status=400)
    sale = Sale.objects.filter(id=sale_id, company=request.user).first()
    if not sale:
        return JsonResponse({"success": False, "error": "Vente introuvable"}, status=404)
    invoice = Invoice.objects.create(
        company=request.user,
        sale=sale,
        invoice_number=invoice_number,
        due_date=due_date,
        status=status,
    )
    return JsonResponse({"success": True, "invoice_id": invoice.id})

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
