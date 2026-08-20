import json
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

import requests as http_requests

from django.conf import settings
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth, TruncDate
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail

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
    Subscription,
    SubscriptionPayment,
    SUBSCRIPTION_PLAN_CHOICES,
    SUBSCRIPTION_PLAN_PRICES,
    TRIAL_DURATION_DAYS,
    PromoCode,
    PromoCodeRedemption,
    redeem_promo_code,
)

# ═══════════════════════════════════════════════════════════════
# Assistant IA (Gemini) — function calling sur les données de l'entreprise
# ═══════════════════════════════════════════════════════════════

GEMINI_API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

CURRENCY_SYMBOLS = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}


def _ai_parse_date(value):
    """Convertit une chaine 'AAAA-MM-JJ' en date. Retourne None si invalide/absente."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _ai_money(value):
    """Convertit proprement un Decimal/None en float pour la sérialisation JSON."""
    if value is None:
        return 0.0
    return float(value)


def _ai_tool_get_ventes(company, args):
    """Liste des ventes de l'entreprise, avec filtres optionnels."""
    qs = Sale.objects.filter(company=company).select_related('client', 'product')

    date_debut = _ai_parse_date(args.get('date_debut'))
    date_fin = _ai_parse_date(args.get('date_fin'))
    if date_debut:
        qs = qs.filter(date__date__gte=date_debut)
    if date_fin:
        qs = qs.filter(date__date__lte=date_fin)

    client_nom = (args.get('client_nom') or '').strip()
    if client_nom:
        qs = qs.filter(client__name__icontains=client_nom)

    totaux = list(qs.values('currency').annotate(total=Sum('total_price'), nombre=Count('id')))
    nombre_total = qs.count()

    try:
        limit = int(args.get('limit') or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))

    ventes = []
    for s in qs.order_by('-date')[:limit]:
        ventes.append({
            'id': s.id,
            'date': s.date.strftime('%Y-%m-%d'),
            'client': s.client.name if s.client else None,
            'produits': s.item_names or (s.product.name if s.product else None),
            'quantite': s.quantity,
            'total': _ai_money(s.total_price),
            'devise': s.currency,
            'agent': s.agent.name if s.agent_id else None,
        })

    return {
        'nombre_total_ventes_correspondantes': nombre_total,
        'totaux_par_devise': [
            {'devise': t['currency'], 'total': _ai_money(t['total']), 'nombre_ventes': t['nombre']}
            for t in totaux
        ],
        'ventes_detaillees': ventes,
        'note': "'ventes_detaillees' est limité aux plus récentes (voir 'limit'); utilise 'totaux_par_devise' pour les montants agrégés exacts.",
    }


def _ai_tool_get_etat_financier(company, args):
    """Vue d'ensemble financière : chiffre d'affaires, factures, impayés, dépenses, marge brute estimée."""
    date_debut = _ai_parse_date(args.get('date_debut'))
    date_fin = _ai_parse_date(args.get('date_fin'))

    sales_qs = Sale.objects.filter(company=company)
    if date_debut:
        sales_qs = sales_qs.filter(date__date__gte=date_debut)
    if date_fin:
        sales_qs = sales_qs.filter(date__date__lte=date_fin)

    ca_par_devise = list(sales_qs.values('currency').annotate(total=Sum('total_price'), nombre=Count('id')))

    supplies_qs = Supply.objects.filter(company=company)
    if date_debut:
        supplies_qs = supplies_qs.filter(date__date__gte=date_debut)
    if date_fin:
        supplies_qs = supplies_qs.filter(date__date__lte=date_fin)
    depenses_par_devise = list(supplies_qs.values('currency').annotate(total=Sum('total_price'), nombre=Count('id')))

    invoices_qs = Invoice.objects.filter(company=company, sale__in=sales_qs).select_related('sale')
    statut_counts = {row['status']: row['nb'] for row in invoices_qs.values('status').annotate(nb=Count('id'))}

    impayes_par_devise = {}
    for inv in invoices_qs:
        if inv.status != 'paid' and inv.sale:
            devise = inv.sale.currency
            impayes_par_devise[devise] = impayes_par_devise.get(devise, Decimal('0.00')) + inv.balance_due

    ca_map = {row['currency']: row['total'] or Decimal('0.00') for row in ca_par_devise}
    dep_map = {row['currency']: row['total'] or Decimal('0.00') for row in depenses_par_devise}
    devises = set(ca_map) | set(dep_map)
    marge_brute_estimee = [
        {
            'devise': d,
            'chiffre_affaires': _ai_money(ca_map.get(d, Decimal('0.00'))),
            'depenses_approvisionnement': _ai_money(dep_map.get(d, Decimal('0.00'))),
            'marge_estimee': _ai_money(ca_map.get(d, Decimal('0.00')) - dep_map.get(d, Decimal('0.00'))),
        }
        for d in devises
    ]

    return {
        'periode': {
            'date_debut': date_debut.isoformat() if date_debut else 'depuis toujours',
            'date_fin': date_fin.isoformat() if date_fin else "aujourd'hui",
        },
        'chiffre_affaires_par_devise': [
            {'devise': r['currency'], 'total': _ai_money(r['total']), 'nombre_ventes': r['nombre']}
            for r in ca_par_devise
        ],
        'depenses_approvisionnement_par_devise': [
            {'devise': r['currency'], 'total': _ai_money(r['total']), 'nombre_achats': r['nombre']}
            for r in depenses_par_devise
        ],
        'marge_brute_estimee_par_devise': marge_brute_estimee,
        'factures_par_statut': {
            'en_attente': statut_counts.get('pending', 0),
            'partiellement_payees': statut_counts.get('partial', 0),
            'payees': statut_counts.get('paid', 0),
            'en_retard': statut_counts.get('overdue', 0),
        },
        'montant_impaye_par_devise': [
            {'devise': d, 'montant_restant_du': _ai_money(v)} for d, v in impayes_par_devise.items()
        ],
        'avertissement': "La marge estimée compare le CA et les achats de la période, sans tenir compte des charges fixes ni des stocks déjà en réserve : c'est une approximation, pas une comptabilité exacte.",
    }


def _ai_tool_get_produits_stock(company, args):
    """État du stock produits, avec détection des stocks bas."""
    try:
        seuil = int(args.get('seuil_alerte') or 5)
    except (TypeError, ValueError):
        seuil = 5

    produits = Product.objects.filter(company=company).order_by('stock_quantity')
    liste = [
        {
            'nom': p.name,
            'stock_actuel': p.stock_quantity,
            'prix_unitaire': _ai_money(p.price),
            'devise': p.currency,
        }
        for p in produits
    ]
    stock_bas = [p for p in liste if p['stock_actuel'] <= seuil]

    return {
        'nombre_produits_total': len(liste),
        'seuil_alerte_utilise': seuil,
        'produits_stock_bas': stock_bas,
        'tous_les_produits': liste[:50],
    }


def _ai_tool_get_clients(company, args):
    """Classement des clients par montant total acheté."""
    try:
        limit = int(args.get('limit') or 15)
    except (TypeError, ValueError):
        limit = 15
    limit = max(1, min(limit, 50))

    clients = (
        Client.objects.filter(company=company)
        .annotate(total_achats=Sum('sales__total_price'), nombre_ventes=Count('sales'))
        .order_by('-total_achats')[:limit]
    )
    liste = [
        {
            'nom': c.name,
            'boutique': c.shop_name or None,
            'telephone': c.phone or None,
            'total_achats': _ai_money(c.total_achats),
            'nombre_ventes': c.nombre_ventes,
        }
        for c in clients
    ]
    return {'nombre_clients_total': Client.objects.filter(company=company).count(), 'meilleurs_clients': liste}


def _ai_tool_get_factures(company, args):
    """Liste des factures, filtrable par statut (pending, partial, paid, overdue)."""
    qs = Invoice.objects.filter(company=company).select_related('sale', 'sale__client')

    statut = (args.get('statut') or '').strip().lower()
    if statut in ('pending', 'partial', 'paid', 'overdue'):
        qs = qs.filter(status=statut)

    total = qs.count()

    try:
        limit = int(args.get('limit') or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))

    liste = []
    for inv in qs.order_by('-issued_date')[:limit]:
        liste.append({
            'numero': inv.invoice_number,
            'client': inv.sale.client.name if inv.sale and inv.sale.client else None,
            'montant_total': _ai_money(inv.sale.total_price) if inv.sale else 0.0,
            'montant_paye': _ai_money(inv.amount_paid),
            'reste_a_payer': _ai_money(inv.balance_due),
            'devise': inv.sale.currency if inv.sale else None,
            'statut': inv.status,
            'echeance': inv.due_date.isoformat() if inv.due_date else None,
        })

    return {'nombre_total_correspondant': total, 'factures': liste}


AI_TOOL_FUNCTIONS = {
    'get_ventes': _ai_tool_get_ventes,
    'get_etat_financier': _ai_tool_get_etat_financier,
    'get_produits_stock': _ai_tool_get_produits_stock,
    'get_clients': _ai_tool_get_clients,
    'get_factures': _ai_tool_get_factures,
}

AI_FUNCTION_DECLARATIONS = [
    {
        "name": "get_ventes",
        "description": "Retourne la liste des ventes de l'entreprise connectée, avec les totaux agrégés par devise. Utilise cette fonction pour toute question sur les ventes, une période, ou un client précis.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date_debut": {"type": "STRING", "description": "Date de début au format AAAA-MM-JJ (optionnel)."},
                "date_fin": {"type": "STRING", "description": "Date de fin au format AAAA-MM-JJ (optionnel)."},
                "client_nom": {"type": "STRING", "description": "Filtrer sur le nom d'un client précis (optionnel)."},
                "limit": {"type": "INTEGER", "description": "Nombre maximum de ventes détaillées à retourner (défaut 20, max 100)."},
            },
        },
    },
    {
        "name": "get_etat_financier",
        "description": "Retourne l'état financier de l'entreprise : chiffre d'affaires, dépenses d'approvisionnement, marge brute estimée, statut des factures (payées/en attente/en retard) et montants impayés. Utilise cette fonction pour toute demande d'analyse financière, de rentabilité ou de santé de l'entreprise.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date_debut": {"type": "STRING", "description": "Date de début au format AAAA-MM-JJ (optionnel, sinon depuis toujours)."},
                "date_fin": {"type": "STRING", "description": "Date de fin au format AAAA-MM-JJ (optionnel, sinon aujourd'hui)."},
            },
        },
    },
    {
        "name": "get_produits_stock",
        "description": "Retourne la liste des produits avec leur quantité en stock, et identifie les produits en stock bas. Utilise cette fonction pour toute question sur le stock, les ruptures ou le réapprovisionnement.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "seuil_alerte": {"type": "INTEGER", "description": "Quantité en-dessous de laquelle un produit est considéré en stock bas (défaut 5)."},
            },
        },
    },
    {
        "name": "get_clients",
        "description": "Retourne le classement des clients par montant total acheté. Utilise cette fonction pour identifier les meilleurs clients ou analyser la clientèle.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {"type": "INTEGER", "description": "Nombre maximum de clients à retourner (défaut 15, max 50)."},
            },
        },
    },
    {
        "name": "get_factures",
        "description": "Retourne la liste des factures, avec possibilité de filtrer par statut. Utilise cette fonction pour toute question sur les factures, les paiements en attente ou en retard.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "statut": {"type": "STRING", "description": "Filtrer par statut : 'pending' (en attente), 'partial' (partiel), 'paid' (payée), 'overdue' (en retard). Laisser vide pour tout retourner."},
                "limit": {"type": "INTEGER", "description": "Nombre maximum de factures à retourner (défaut 20, max 100)."},
            },
        },
    },
]

AI_SYSTEM_PROMPT = """Tu es l'assistant IA intégré à InvoiceApp, une application de facturation et de gestion \
commerciale. Tu discutes actuellement avec l'entreprise « {company_name} » (devise par défaut : {currency}), \
connectée à son propre tableau de bord. La date du jour est {today}.

Tu as accès à des fonctions qui interrogent en temps réel la base de données de CETTE entreprise (ventes, \
factures, stock, clients, finances). Règles impératives :
- Utilise TOUJOURS les fonctions disponibles pour obtenir des chiffres réels avant de répondre à une question \
factuelle. Ne invente JAMAIS de chiffres, de noms de clients ou de montants.
- Si une question nécessite plusieurs angles (ex: état financier complet), tu peux appeler plusieurs fonctions \
à la suite avant de répondre.
- Réponds en français, de façon claire, concise et actionnable. Utilise des puces pour les listes.
- Formate toujours les montants avec leur devise.
- Quand on te demande une analyse ou un diagnostic, termine par 1 à 3 recommandations concrètes et réalistes \
(ex: relancer tel client en retard de paiement, réapprovisionner tel produit, ajuster tel prix), basées \
uniquement sur les données récupérées.
- Si les données manquent ou sont vides, dis-le simplement plutôt que de spéculer.
- Reste dans le contexte de la conversation précédente : l'utilisateur peut naviguer entre les pages de l'app, \
la conversation continue normalement."""


def _ai_run_tool(name, company, args):
    fn = AI_TOOL_FUNCTIONS.get(name)
    if not fn:
        return {'erreur': f"Fonction inconnue: {name}"}
    try:
        return fn(company, args or {})
    except Exception as exc:  # pragma: no cover - garde-fou pour ne jamais casser la boucle agent
        return {'erreur': f"Erreur lors de l'exécution de {name}: {exc}"}


@require_http_methods(["GET"])
@login_required
def ai_chat_init(request):
    """Endpoint léger appelé au chargement du widget pour garantir la présence du cookie CSRF."""
    from django.middleware.csrf import get_token
    get_token(request)
    return JsonResponse({'ok': True, 'ai_enabled': bool(settings.GEMINI_API_KEY)})


@require_http_methods(["POST"])
@login_required
def ai_chat_api(request):
    """Point d'entrée du chat IA flottant. Pilote Gemini avec function calling sur les données de l'entreprise."""
    if not settings.GEMINI_API_KEY:
        return JsonResponse({
            'reply': "L'assistant IA n'est pas encore configuré. Ajoutez votre clé GEMINI_API_KEY dans le fichier .env du serveur pour l'activer.",
            'contents': [],
        })

    try:
        payload_in = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': "Requête invalide."}, status=400)

    message = (payload_in.get('message') or '').strip()
    contents = payload_in.get('contents') or []
    if not isinstance(contents, list):
        contents = []
    # Garde-fou : on borne la taille de l'historique renvoyé par le client.
    contents = contents[-60:]

    if not message:
        return JsonResponse({'error': "Message vide."}, status=400)
    if len(message) > 4000:
        message = message[:4000]

    contents.append({'role': 'user', 'parts': [{'text': message}]})

    company = request.user
    system_text = AI_SYSTEM_PROMPT.format(
        company_name=company.company_name,
        currency=getattr(company, 'default_currency', 'EUR'),
        today=timezone.now().date().isoformat(),
    )

    url = GEMINI_API_URL_TEMPLATE.format(model=settings.GEMINI_MODEL, key=settings.GEMINI_API_KEY)
    headers = {'Content-Type': 'application/json'}

    final_text = None
    for _ in range(6):
        body = {
            'system_instruction': {'parts': [{'text': system_text}]},
            'contents': contents,
            'tools': [{'function_declarations': AI_FUNCTION_DECLARATIONS}],
            'generationConfig': {'temperature': 0.3},
        }
        try:
            resp = http_requests.post(url, json=body, headers=headers, timeout=30)
        except http_requests.RequestException:
            return JsonResponse({
                'reply': "Impossible de contacter le service IA pour le moment. Réessaie dans un instant.",
                'contents': contents[:-1],
            })

        if resp.status_code != 200:
            return JsonResponse({
                'reply': "Le service IA a renvoyé une erreur. Vérifie la clé GEMINI_API_KEY et réessaie.",
                'contents': contents[:-1],
            })

        data = resp.json()
        candidates = data.get('candidates') or []
        if not candidates:
            final_text = "Je n'ai pas pu générer de réponse. Peux-tu reformuler ta question ?"
            break

        model_content = candidates[0].get('content') or {'role': 'model', 'parts': []}
        parts = model_content.get('parts') or []
        contents.append({'role': 'model', 'parts': parts})

        function_call_parts = [p for p in parts if 'functionCall' in p]
        if not function_call_parts:
            final_text = ''.join(p.get('text', '') for p in parts if 'text' in p).strip()
            if not final_text:
                final_text = "Je n'ai pas de réponse à formuler pour l'instant."
            break

        response_parts = []
        for p in function_call_parts:
            fc = p['functionCall']
            fname = fc.get('name')
            fargs = fc.get('args') or {}
            result = _ai_run_tool(fname, company, fargs)
            response_parts.append({'functionResponse': {'name': fname, 'response': result}})
        contents.append({'role': 'user', 'parts': response_parts})
    else:
        final_text = "L'analyse demande trop d'étapes, essaie de poser une question plus précise."

    return JsonResponse({'reply': final_text, 'contents': contents})


def landing(request):
    """Landing page - visible to all visitors"""
    return render(request, 'landing.html')

def _send_activation_email(user):
    """Envoie l'email contenant le lien d'activation du compte entreprise."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    activation_link = settings.SITE_BASE_URL.rstrip('/') + reverse('activate_account', kwargs={'uidb64': uid, 'token': token})

    subject = "Activez votre compte InvoiceApp"
    message = (
        f"Bonjour {user.company_name},\n\n"
        f"Merci de votre inscription sur InvoiceApp !\n"
        f"Cliquez sur le lien ci-dessous pour activer votre compte et commencer à l'utiliser :\n\n"
        f"{activation_link}\n\n"
        f"Si vous n'êtes pas à l'origine de cette inscription, ignorez simplement cet email.\n"
    )
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)


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
        subscription_plan = request.POST.get("subscription_plan", "monthly")
        promo_code_input = request.POST.get("promo_code", "").strip()
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

        if subscription_plan not in dict(SUBSCRIPTION_PLAN_CHOICES).keys():
            subscription_plan = "monthly"

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
            is_active=False,
        )
        Subscription.objects.create(
            company=user,
            plan=subscription_plan,
            trial_end_date=timezone.now() + timezone.timedelta(days=TRIAL_DURATION_DAYS),
        )

        promo_message = None
        if promo_code_input:
            promo_success, promo_message = redeem_promo_code(user, promo_code_input)
            if not promo_success:
                # On ne bloque pas la création du compte pour un code promo invalide,
                # on informe simplement l'entreprise dans la réponse.
                pass

        try:
            _send_activation_email(user)
            activation_email_sent = True
        except Exception:
            # On ne bloque jamais la création du compte si l'envoi d'email échoue,
            # mais on informe le front pour proposer un renvoi manuel.
            activation_email_sent = False

        return JsonResponse({
            "success": True,
            "message": "Compte créé. Vérifiez votre boîte mail pour activer votre compte.",
            "user_id": user.id,
            "promo_message": promo_message,
            "activation_email_sent": activation_email_sent,
        })

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
            # Le compte existe peut-être mais n'est pas encore activé : authenticate()
            # renvoie None dans ce cas (ModelBackend rejette les comptes is_active=False).
            existing = User.objects.filter(username=email).first()
            if existing and not existing.is_active and existing.check_password(password):
                return JsonResponse({
                    "success": False,
                    "error": "Votre compte n'est pas encore activé. Vérifiez votre boîte mail (et vos spams) pour le lien d'activation.",
                    "inactive": True,
                }, status=403)
            return JsonResponse({"success": False, "error": "Identifiants invalides"}, status=400)

        login(request, user)
        return JsonResponse({"success": True, "message": "Connecté", "redirect": '/dashboard/'} )

    return render(request, 'login.html')


# ═══════════════════════════════════════════════════════════════
# Récupération de mot de passe oublié (par email)
# ═══════════════════════════════════════════════════════════════

@require_http_methods(["GET", "POST"])
def forgot_password(request):
    """Demande de réinitialisation : envoie un email avec un lien à usage unique si le
    compte existe. La réponse est identique que l'email existe ou non, pour ne pas
    révéler quelles adresses sont enregistrées sur la plateforme."""
    if request.method == "GET":
        return render(request, 'forgot_password.html')

    email = (request.POST.get("email") or "").strip()
    if not email:
        return JsonResponse({"success": False, "error": "Veuillez saisir votre adresse email."}, status=400)

    generic_message = "Si un compte existe avec cette adresse, un email de réinitialisation vient d'être envoyé."
    user = User.objects.filter(email__iexact=email).first()

    if user is not None:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_link = settings.SITE_BASE_URL.rstrip('/') + reverse('reset_password_confirm', kwargs={'uidb64': uid, 'token': token})

        subject = "Réinitialisation de votre mot de passe"
        message = (
            f"Bonjour {user.company_name},\n\n"
            f"Vous avez demandé la réinitialisation du mot de passe de votre compte.\n"
            f"Cliquez sur le lien ci-dessous pour choisir un nouveau mot de passe "
            f"(valable {settings.PASSWORD_RESET_TIMEOUT // 3600} heures) :\n\n"
            f"{reset_link}\n\n"
            f"Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet email : "
            f"votre mot de passe actuel restera inchangé.\n"
        )
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        except Exception:
            # On ne révèle jamais un éventuel échec technique à l'utilisateur (évite l'énumération
            # de comptes), mais on ne bloque pas non plus la réponse générique.
            pass

    return JsonResponse({"success": True, "message": generic_message})


@require_http_methods(["GET", "POST"])
def reset_password_confirm(request, uidb64, token):
    """Page atteinte via le lien reçu par email : vérifie le token puis permet de
    définir un nouveau mot de passe."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    token_valid = user is not None and default_token_generator.check_token(user, token)

    if request.method == "GET":
        return render(request, 'reset_password_confirm.html', {'token_valid': token_valid})

    if not token_valid:
        return JsonResponse({"success": False, "error": "Ce lien de réinitialisation est invalide ou a expiré."}, status=400)

    new_password = request.POST.get("new_password")
    confirm_password = request.POST.get("confirm_password")
    if not new_password:
        return JsonResponse({"success": False, "error": "Veuillez saisir un nouveau mot de passe."}, status=400)
    if new_password != confirm_password:
        return JsonResponse({"success": False, "error": "Les mots de passe ne correspondent pas."}, status=400)
    if len(new_password) < 8:
        return JsonResponse({"success": False, "error": "Le mot de passe doit contenir au moins 8 caractères."}, status=400)

    user.set_password(new_password)
    user.save()
    return JsonResponse({"success": True, "message": "Mot de passe réinitialisé. Vous pouvez maintenant vous connecter."})


# ═══════════════════════════════════════════════════════════════
# Activation du compte entreprise (par email, après inscription)
# ═══════════════════════════════════════════════════════════════

@require_http_methods(["GET"])
def activate_account(request, uidb64, token):
    """Lien reçu par email après inscription : active le compte et connecte
    directement l'entreprise si le lien est valide."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])
        login(request, user)
        return redirect('dashboard')

    return render(request, 'activation_invalid.html', {
        'email': user.email if user else '',
    })


@require_http_methods(["POST"])
def resend_activation_email(request):
    """Renvoie un email d'activation. Réponse générique (même si l'email n'existe
    pas ou que le compte est déjà actif) pour ne pas révéler quels comptes existent."""
    email = (request.POST.get("email") or "").strip()
    if not email:
        return JsonResponse({"success": False, "error": "Veuillez saisir votre adresse email."}, status=400)

    generic_message = "Si un compte inactif existe avec cette adresse, un email d'activation vient d'être renvoyé."
    user = User.objects.filter(email__iexact=email, is_active=False).first()
    if user is not None:
        try:
            _send_activation_email(user)
        except Exception:
            pass

    return JsonResponse({"success": True, "message": generic_message})


# ═══════════════════════════════════════════════════════════════
# Abonnement & paiement MoneyFusion (FusionPay)
# ═══════════════════════════════════════════════════════════════

def _moneyfusion_configured():
    return bool(settings.MONEYFUSION_API_URL)


@require_http_methods(["GET"])
@login_required
def subscription_page(request):
    """Page dédiée à l'abonnement : statut de l'essai/abonnement + paiement MoneyFusion."""
    subscription = getattr(request.user, 'subscription', None)
    recent_payments = SubscriptionPayment.objects.filter(company=request.user)[:10]
    promo_redemptions = PromoCodeRedemption.objects.filter(company=request.user).select_related('promo_code')
    context = {
        'subscription': subscription,
        'plans': [
            {'code': 'monthly', 'label': 'Mensuel', 'price': SUBSCRIPTION_PLAN_PRICES['monthly']},
            {'code': 'annual', 'label': 'Annuel', 'price': SUBSCRIPTION_PLAN_PRICES['annual']},
        ],
        'recent_payments': recent_payments,
        'promo_redemptions': promo_redemptions,
        'moneyfusion_configured': _moneyfusion_configured(),
    }
    return render(request, 'subscription.html', context)


@require_http_methods(["POST"])
@login_required
def apply_promo_code(request):
    """Applique un code promo saisi par l'entreprise depuis la page d'abonnement."""
    code = request.POST.get("code", "")
    success, message = redeem_promo_code(request.user, code)
    if success:
        return JsonResponse({"success": True, "message": message})
    return JsonResponse({"success": False, "error": message}, status=400)


# ═══════════════════════════════════════════════════════════════
# Gestion des codes promo (réservé au staff — via /admin-tools/)
# ═══════════════════════════════════════════════════════════════

@require_http_methods(["GET"])
@staff_member_required
def promo_codes_admin(request):
    """Liste des codes promo + formulaire de génération rapide (réservé au staff)."""
    codes = PromoCode.objects.all().prefetch_related('redemptions')
    return render(request, 'promo_codes_admin.html', {'codes': codes})


@require_http_methods(["POST"])
@staff_member_required
def create_promo_code(request):
    """Génère un nouveau code promo avec la durée choisie."""
    try:
        duration_days = int(request.POST.get("duration_days", "0"))
    except (TypeError, ValueError):
        duration_days = 0
    if duration_days <= 0:
        return JsonResponse({"success": False, "error": "La durée doit être un nombre de jours positif."}, status=400)

    note = request.POST.get("note", "").strip()[:255]
    custom_code = request.POST.get("code", "").strip().upper()

    max_redemptions_raw = request.POST.get("max_redemptions", "").strip()
    max_redemptions = None
    if max_redemptions_raw:
        try:
            max_redemptions = int(max_redemptions_raw)
            if max_redemptions <= 0:
                max_redemptions = None
        except ValueError:
            max_redemptions = None

    valid_until_raw = request.POST.get("valid_until", "").strip()
    valid_until = None
    if valid_until_raw:
        # Format attendu depuis <input type="date"> : YYYY-MM-DD
        try:
            from datetime import datetime
            valid_until = timezone.make_aware(datetime.strptime(valid_until_raw, "%Y-%m-%d"))
        except ValueError:
            valid_until = None

    kwargs = {
        'duration_days': duration_days,
        'note': note,
        'max_redemptions': max_redemptions,
        'valid_until': valid_until,
    }
    if custom_code:
        if PromoCode.objects.filter(code__iexact=custom_code).exists():
            return JsonResponse({"success": False, "error": "Ce code existe déjà."}, status=400)
        kwargs['code'] = custom_code

    promo = PromoCode.objects.create(**kwargs)
    return JsonResponse({"success": True, "code": promo.code, "id": promo.id})


@require_http_methods(["POST"])
@staff_member_required
def toggle_promo_code(request, promo_id):
    """Active/désactive un code promo (bascule)."""
    try:
        promo = PromoCode.objects.get(id=promo_id)
    except PromoCode.DoesNotExist:
        return JsonResponse({"success": False, "error": "Code promo introuvable."}, status=404)
    promo.is_active = not promo.is_active
    promo.save(update_fields=['is_active'])
    return JsonResponse({"success": True, "is_active": promo.is_active})


@require_http_methods(["POST"])
@login_required
def initiate_subscription_payment(request):
    """Crée une transaction MoneyFusion pour le plan choisi et renvoie l'URL de paiement
    vers laquelle le navigateur doit être redirigé (intégration par redirection)."""
    if not _moneyfusion_configured():
        return JsonResponse({
            "success": False,
            "error": "Le paiement en ligne n'est pas encore configuré. Contactez l'administrateur.",
        }, status=503)

    plan = request.POST.get("plan")
    if plan not in dict(SUBSCRIPTION_PLAN_CHOICES).keys():
        return JsonResponse({"success": False, "error": "Plan invalide"}, status=400)

    subscription, _ = Subscription.objects.get_or_create(
        company=request.user,
        defaults={'plan': plan, 'trial_end_date': timezone.now() + timezone.timedelta(days=TRIAL_DURATION_DAYS)},
    )

    amount = int(SUBSCRIPTION_PLAN_PRICES[plan])
    transaction_id = f"SUB-{request.user.id}-{uuid.uuid4().hex[:12]}"

    payment = SubscriptionPayment.objects.create(
        company=request.user,
        plan=plan,
        amount=amount,
        transaction_id=transaction_id,
        status='pending',
    )

    user = request.user
    plan_label = dict(SUBSCRIPTION_PLAN_CHOICES).get(plan)

    payload = {
        "totalPrice": amount,
        "article": [{f"Abonnement {plan_label}": amount}],
        "numeroSend": (user.phone or "0000000000").replace(" ", ""),
        "nomclient": user.company_name or user.email or "Client",
        "personal_Info": [{"userId": str(user.id), "orderId": transaction_id}],
        "return_url": settings.SITE_BASE_URL.rstrip('/') + reverse('moneyfusion_return'),
        "webhook_url": settings.SITE_BASE_URL.rstrip('/') + reverse('moneyfusion_webhook'),
    }

    try:
        response = http_requests.post(settings.MONEYFUSION_API_URL, json=payload, timeout=20)
        data = response.json()
    except (http_requests.RequestException, ValueError):
        payment.status = 'failed'
        payment.save(update_fields=['status', 'updated_at'])
        return JsonResponse({"success": False, "error": "Impossible de contacter MoneyFusion. Réessayez."}, status=502)

    if not data.get("statut"):
        payment.status = 'failed'
        payment.save(update_fields=['status', 'updated_at'])
        return JsonResponse({"success": False, "error": data.get("message") or "Échec de l'initialisation du paiement."}, status=400)

    provider_token = data.get("token", "")
    payment.provider_token = provider_token
    payment.save(update_fields=['provider_token', 'updated_at'])

    payment_url = data.get("url")
    return JsonResponse({"success": True, "payment_url": payment_url, "transaction_id": transaction_id})


def _verify_and_apply_payment(payment):
    """Vérifie une transaction auprès de MoneyFusion et applique le résultat (idempotent).
    `payment` est déjà chargé (SubscriptionPayment) — évite une seconde requête en base."""
    if payment is None or payment.status == 'success' or not payment.provider_token:
        return payment  # rien à faire (déjà traité, ou pas encore de token MoneyFusion)

    status_url = settings.MONEYFUSION_STATUS_CHECK_TEMPLATE.format(token=payment.provider_token)
    try:
        response = http_requests.get(status_url, timeout=20)
        data = response.json()
    except (http_requests.RequestException, ValueError):
        return payment

    result = data.get("data", {})
    provider_status = result.get("statut")  # "paid" | "pending" | "failed" | "no paid"
    payment.payment_method = result.get("moyen", "") or payment.payment_method
    payment.operator_id = result.get("numeroTransaction", "") or payment.operator_id

    if provider_status == "paid":
        payment.status = 'success'
        payment.save(update_fields=['status', 'payment_method', 'operator_id', 'updated_at'])
        subscription = getattr(payment.company, 'subscription', None)
        if subscription:
            subscription.plan = payment.plan
            subscription.save(update_fields=['plan', 'updated_at'])
            subscription.extend_after_payment()
    elif provider_status in ("failed", "no paid"):
        payment.status = 'failed'
        payment.save(update_fields=['status', 'payment_method', 'operator_id', 'updated_at'])
    else:
        payment.save(update_fields=['payment_method', 'operator_id', 'updated_at'])

    return payment


@csrf_exempt
@require_http_methods(["POST"])
def moneyfusion_webhook(request):
    """Webhook appelé par les serveurs de MoneyFusion (webhook_url fourni à l'initialisation)
    à chaque changement de statut. Ne jamais faire confiance au contenu brut de la requête :
    on ne l'utilise que pour retrouver la transaction, puis on revérifie via l'API MoneyFusion."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        body = request.POST

    provider_token = body.get("tokenPay") or body.get("token")
    if not provider_token:
        return HttpResponse("tokenPay manquant", status=400)

    payment = SubscriptionPayment.objects.select_related('company', 'company__subscription').filter(
        provider_token=provider_token
    ).first()
    if payment is None:
        return HttpResponse("Transaction inconnue", status=404)

    _verify_and_apply_payment(payment)
    return HttpResponse("OK")


@require_http_methods(["GET", "POST"])
@login_required
def moneyfusion_return(request):
    """Page où le client est redirigé après avoir payé (return_url — MoneyFusion y ajoute ?token=...)."""
    provider_token = request.GET.get("token") or request.POST.get("token")

    payment = None
    if provider_token:
        payment = SubscriptionPayment.objects.select_related('company', 'company__subscription').filter(
            company=request.user, provider_token=provider_token
        ).first()
    if payment is None:
        payment = SubscriptionPayment.objects.filter(company=request.user).order_by('-created_at').first()

    # MoneyFusion ne garantit pas l'ordre webhook/retour : on revérifie ici aussi par sécurité.
    if payment and payment.status == 'pending':
        payment = _verify_and_apply_payment(payment)

    return render(request, 'subscription_return.html', {'payment': payment})

MONTH_LABELS_FR = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']


def _monthly_revenue(user, year):
    """Retourne (labels, valeurs) du chiffre d'affaires mensuel pour l'année donnée."""
    rows = (
        Sale.objects.filter(company=user, date__year=year)
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('total_price'))
    )
    totals_by_month = {row['month'].month: float(row['total'] or 0) for row in rows if row['month']}
    data = [totals_by_month.get(m, 0) for m in range(1, 13)]
    return MONTH_LABELS_FR, data


def _sales_breakdown_by_product(user, limit=4):
    """Retourne (labels, valeurs) de la répartition des ventes par produit (top N + 'Autres')."""
    rows = list(
        SaleItem.objects.filter(sale__company=user)
        .values('product__name')
        .annotate(total=Sum('total_price'))
        .order_by('-total')
    )
    if not rows:
        return [], []

    top_rows = rows[:limit]
    rest_rows = rows[limit:]
    labels = [row['product__name'] or 'Produit supprimé' for row in top_rows]
    values = [float(row['total'] or 0) for row in top_rows]

    if rest_rows:
        rest_total = sum(float(row['total'] or 0) for row in rest_rows)
        labels.append('Autres')
        values.append(rest_total)

    return labels, values


def _revenue_by_period(user, start_date, end_date):
    """Retourne (labels, valeurs) du chiffre d'affaires jour par jour entre deux dates précises (incluses)."""
    rows = (
        Sale.objects.filter(company=user, date__date__gte=start_date, date__date__lte=end_date)
        .annotate(day=TruncDate('date'))
        .values('day')
        .annotate(total=Sum('total_price'))
    )
    totals_by_day = {row['day']: float(row['total'] or 0) for row in rows if row['day']}
    labels, data = [], []
    current = start_date
    while current <= end_date:
        labels.append(current.strftime('%d/%m/%Y'))
        data.append(totals_by_day.get(current, 0))
        current += timedelta(days=1)
    return labels, data


def _top_products(user, limit=5):
    """Retourne (noms, quantités vendues, ca) des produits les plus vendus, triés par quantité décroissante."""
    rows = list(
        SaleItem.objects.filter(sale__company=user)
        .values('product__id', 'product__name')
        .annotate(qty=Sum('quantity'), total_ca=Sum('total_price'))
        .order_by('-qty')[:limit]
    )
    names = [row['product__name'] or 'Produit supprimé' for row in rows]
    qty = [row['qty'] or 0 for row in rows]
    ca = [float(row['total_ca'] or 0) for row in rows]
    return names, qty, ca


def _agents_performance(user):
    """Retourne (noms, nb_ventes, ca, rôles) des agents ayant vendu ce mois-ci, triés par CA décroissant."""
    now = timezone.now()
    rows = (
        Sale.objects.filter(company=user, agent__isnull=False, date__year=now.year, date__month=now.month)
        .values('agent__id', 'agent__name', 'agent__role__name')
        .annotate(sales_count=Count('id'), total_ca=Sum('total_price'))
        .order_by('-total_ca')
    )
    names = [row['agent__name'] for row in rows]
    sales = [row['sales_count'] for row in rows]
    ca = [float(row['total_ca'] or 0) for row in rows]
    roles = [row['agent__role__name'] or '' for row in rows]
    return names, sales, ca, roles


@require_http_methods(["GET"])
@login_required
def dashboard(request):
    user = request.user
    now = timezone.now()

    # Période par défaut du graphique CA : du 1er du mois en cours à aujourd'hui.
    period_end = now.date()
    period_start = period_end.replace(day=1)
    ca_labels, ca_data = _revenue_by_period(user, period_start, period_end)
    cat_labels, cat_values = _sales_breakdown_by_product(user)
    agent_names, agent_sales, agent_ca, agent_roles = _agents_performance(user)
    top_product_names, top_product_qty, top_product_ca = _top_products(user)

    currency_symbols = {'EUR': '€', 'USD': '$', 'XOF': 'FCFA'}
    currency_symbol = currency_symbols.get(user.default_currency, user.default_currency)

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
        'currency_symbol': currency_symbol,
        'ca_period_labels': json.dumps(ca_labels),
        'ca_period_data': json.dumps(ca_data),
        'ca_period_start': period_start.isoformat(),
        'ca_period_end': period_end.isoformat(),
        'sales_categories': json.dumps(cat_labels),
        'sales_cat_values': json.dumps(cat_values),
        'agents_names': json.dumps(agent_names),
        'agents_sales': json.dumps(agent_sales),
        'agents_ca': json.dumps(agent_ca),
        'agents_roles': json.dumps(agent_roles),
        'top_products_names': json.dumps(top_product_names),
        'top_products_qty': json.dumps(top_product_qty),
        'top_products_ca': json.dumps(top_product_ca),
    }
    return render(request, 'dashboard.html', context)

@require_http_methods(["GET"])
@login_required
def api_dashboard_ca(request):
    """Retourne le CA jour par jour, en JSON, pour une période précise choisie sur le dashboard."""
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')

    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else None
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else None
    except ValueError:
        return JsonResponse({'error': "Format de date invalide (attendu AAAA-MM-JJ)"}, status=400)

    today = timezone.now().date()
    if not start_date or not end_date:
        start_date = start_date or today.replace(day=1)
        end_date = end_date or today

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    if (end_date - start_date).days > 366:
        return JsonResponse({'error': "La période ne peut pas dépasser 366 jours"}, status=400)

    labels, data = _revenue_by_period(request.user, start_date, end_date)
    return JsonResponse({'labels': labels, 'values': data})

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




def _build_invoice_pdf_bytes(invoice):
    """Génère le PDF de la facture et retourne ses octets bruts (réutilisable pour
    le téléchargement HTTP ou tout autre usage futur)."""
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
    return buffer.getvalue()


def _render_invoice_pdf(invoice):
    """Réponse HTTP de téléchargement du PDF de la facture."""
    pdf_bytes = _build_invoice_pdf_bytes(invoice)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
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
    products = user.products.all()
    agent_stocks = AgentStock.objects.filter(agent__company=user).select_related('agent', 'product').filter(quantity__gt=0).order_by('agent__name', 'product__name')
    loads = StockLoad.objects.filter(company=user).select_related('agent').prefetch_related('items__product').order_by('-date')[:30]
    returns = StockReturn.objects.filter(company=user).select_related('agent').prefetch_related('items__product').order_by('-date')[:30]

    context = {
        'company_name': user.company_name,
        'company_logo_url': user.logo.url if user.logo else None,
        'agents': agents,
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
        load = StockLoad.objects.create(company=user, agent=agent, note=note)

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