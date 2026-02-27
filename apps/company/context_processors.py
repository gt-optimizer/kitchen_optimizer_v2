def atelier_context(request):
    if not request.user.is_authenticated:
        return {}

    current_company = None
    companies = request.user.get_companies()
    company_id = request.session.get('current_company_id')

    if company_id:
        current_company = companies.filter(pk=company_id).first()
    if not current_company:
        current_company = companies.first()
        if current_company:
            request.session['current_company_id'] = current_company.pk

    return {
        'current_company':    current_company,
        'user_companies':     companies,
        'user_roles':         [],
        'perms_catalog':      True,
        'perms_purchasing':   True,
        'perms_stock':        True,
        'perms_production':   True,
        'perms_planning':     True,
        'perms_pms':          True,
        'perms_sales':        True,
        'perms_manage_users': True,
        'pms_alerts_count':   0,
        'stock_alerts_count': 0,
    }