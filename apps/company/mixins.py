from functools import wraps
from django.core.exceptions import PermissionDenied
from apps.company.context_processors import atelier_context


def get_current_company(request):
    """Récupère le site actif depuis la session."""
    ctx = atelier_context(request)
    return ctx.get('current_company')


def get_user_roles(request) -> list[str]:
    """
    Retourne la liste des rôles de l'utilisateur sur le site actif.
    Retourne [] si pas de site actif ou pas authentifié.
    """
    if not request.user.is_authenticated:
        return []
    if request.user.is_superuser:
        return ['owner', 'admin', 'production', 'worker', 'cleaning']
    company = get_current_company(request)
    if not company:
        return []
    return list(
        request.user.company_roles
        .filter(company=company)
        .values_list('role', flat=True)
    )


def check_role(request, *roles) -> bool:
    """
    Vérifie si l'utilisateur a au moins un des rôles demandés sur le site actif.

    Usage dans une vue :
        if not check_role(request, 'owner', 'admin'):
            raise PermissionDenied

    Usage dans un template (via context processor) :
        {% if user_roles|has_role:'owner' %}
    """
    if not request.user.is_authenticated:
        return False
    if request.user.is_superuser:
        return True
    user_roles = get_user_roles(request)
    return any(r in user_roles for r in roles)


def require_role(*roles):
    """
    Décorateur de vue — lève PermissionDenied si l'utilisateur n'a pas
    au moins un des rôles demandés sur le site actif.

    Usage :
        @login_required
        @require_role('owner', 'admin')
        def company_list(request): ...

        @login_required
        @require_role('owner', 'admin', 'production')
        def equipment_list(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not check_role(request, *roles):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator