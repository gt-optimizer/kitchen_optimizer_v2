from apps.company.models import Company, UserCompanyRole


def atelier_context(request):
    if not request.user.is_authenticated:
        return {}

    # ── Site actif ────────────────────────────────────────────────────────
    if request.user.is_superuser:
        # Superuser : accès à tous les sites du tenant
        companies = Company.objects.all()
    else:
        companies = request.user.get_companies()

    current_company = None
    company_id = request.session.get('current_company_id')
    if company_id:
        current_company = companies.filter(pk=company_id).first()
    if not current_company:
        current_company = companies.first()
        if current_company:
            request.session['current_company_id'] = current_company.pk

    # ── Rôles sur le site actif ───────────────────────────────────────────
    if request.user.is_superuser:
        roles = {'owner', 'admin', 'production', 'worker', 'cleaning'}
    elif current_company:
        roles = set(request.user.get_roles_for_company(current_company))
    else:
        roles = set()

    # ── Permissions — branchées sur les méthodes User ─────────────────────
    c = current_company  # raccourci

    if c:
        perms_catalog      = request.user.can_manage_catalog(c)
        perms_purchasing   = request.user.can_view_financials(c)
        perms_stock        = request.user.can_record_production(c)
        perms_production   = request.user.can_record_production(c)
        perms_planning     = request.user.can_view_planning(c)
        perms_pms          = request.user.can_record_cleaning(c)
        perms_sales        = request.user.can_import_sales(c)
        perms_company      = request.user.can_manage_users(c)
        perms_manage_users = request.user.can_manage_users(c)
    else:
        # Aucun site actif — on masque tout sauf si superuser
        su = request.user.is_superuser
        perms_catalog = perms_purchasing = perms_stock = su
        perms_production = perms_planning = perms_pms = su
        perms_sales = perms_company = perms_manage_users = su

    return {
        'current_company':    current_company,
        'user_companies':     companies,
        'user_roles':         list(roles),

        'perms_catalog':      perms_catalog,
        'perms_purchasing':   perms_purchasing,
        'perms_stock':        perms_stock,
        'perms_production':   perms_production,
        'perms_planning':     perms_planning,
        'perms_pms':          perms_pms,
        'perms_sales':        perms_sales,
        'perms_company':      perms_company,
        'perms_manage_users': perms_manage_users,

        # Alertes (Redis plus tard)
        'pms_alerts_count':   0,
        'stock_alerts_count': 0,
    }