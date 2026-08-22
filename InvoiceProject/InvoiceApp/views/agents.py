"""
Gestion des agents (vendeurs), de leurs roles et des engins.
"""
from ._common import *  # noqa: F401,F403


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
    if engine_id and not engine:
        return JsonResponse({"success": False, "error": "Engin introuvable"}, status=400)

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
