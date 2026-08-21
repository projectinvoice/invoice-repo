"""
Assistant IA flottant (Gemini + function calling sur les donnees de l'entreprise).
"""
from ._common import *  # noqa: F401,F403


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
