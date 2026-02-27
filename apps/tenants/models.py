from django_tenants.models import TenantMixin, DomainMixin
from django.db import models


class Tenant(TenantMixin):
    """
    Représente un groupe/client (ex: Groupe Boulangeries Martin).
    Un tenant peut avoir plusieurs sites (Company).
    django-tenants crée automatiquement un schema PostgreSQL par tenant.
    """
    name = models.CharField(max_length=100, verbose_name="Nom du groupe")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # django-tenants : crée/supprime le schema PostgreSQL automatiquement
    auto_create_schema = True
    auto_drop_schema = True

    class Meta:
        verbose_name = "Groupe / Client"
        verbose_name_plural = "Groupes / Clients"

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    """
    Domaine associé à un tenant.
    ex: martin.kitchen-optimizer.com → tenant Groupe Martin
    """
    class Meta:
        verbose_name = "Domaine"
        verbose_name_plural = "Domaines"