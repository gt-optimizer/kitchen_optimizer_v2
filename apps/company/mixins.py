from apps.company.context_processors import atelier_context

def get_current_company(request):
    """Récupère le site actif depuis la session."""
    ctx = atelier_context(request)
    return ctx.get('current_company')