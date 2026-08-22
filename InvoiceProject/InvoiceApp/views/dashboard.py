"""
Tableau de bord entreprise et son API de graphique de CA.
"""
from ._common import *  # noqa: F401,F403


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
