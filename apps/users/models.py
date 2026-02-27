from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Utilisateur personnalisé.
    Lié à un tenant (groupe) pour la gestion multi-tenant.
    Les rôles et accès aux sites sont gérés via UserCompanyRole.

    Note : ADMIN (is_superuser=True) a accès total sans vérification de rôle.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
        verbose_name="Groupe",
    )

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        swappable = "AUTH_USER_MODEL"

    def __str__(self):
        return self.username

    def get_roles_for_company(self, company):
        from apps.company.models import UserCompanyRole
        if self.is_superuser:
            return [UserCompanyRole.ADMIN]
        return list(
            self.company_roles.filter(company=company).values_list("role", flat=True)
        )

    def has_role(self, company, role):
        """Vérifie si le user a un rôle spécifique sur un site."""
        if self.is_superuser:
            return True
        return self.company_roles.filter(company=company, role=role).exists()

    def has_any_role(self, company, roles):
        """Vérifie si le user a au moins un des rôles listés."""
        if self.is_superuser:
            return True
        return self.company_roles.filter(company=company, role__in=roles).exists()

    def get_companies(self):
        """Retourne tous les sites auxquels ce user a accès."""
        from apps.company.models import Company
        if self.is_superuser:
            return Company.objects.filter(tenant=self.tenant)
        company_ids = self.company_roles.values_list("company_id", flat=True)
        return Company.objects.filter(pk__in=company_ids)

    # ── Raccourcis sémantiques ─────────────────────────────────────────────────

    def can_manage_catalog(self, company):
        """Peut modifier articles, fournisseurs, recettes."""
        from apps.company.models import UserCompanyRole
        return self.has_any_role(company, [
            UserCompanyRole.OWNER,
            UserCompanyRole.PRODUCTION,
        ])

    def can_view_financials(self, company):
        """Peut voir le dashboard financier (CA, marges, food cost)."""
        from apps.company.models import UserCompanyRole
        return self.has_any_role(company, [UserCompanyRole.OWNER])

    def can_manage_users(self, company):
        """Peut créer/modifier les users du site."""
        from apps.company.models import UserCompanyRole
        return self.has_any_role(company, [UserCompanyRole.OWNER])

    def can_record_production(self, company):
        """Peut saisir des lots de production."""
        from apps.company.models import UserCompanyRole
        return self.has_any_role(company, [
            UserCompanyRole.OWNER,
            UserCompanyRole.PRODUCTION,
            UserCompanyRole.WORKER,
        ])

    def can_record_cleaning(self, company):
        """Peut enregistrer les nettoyages."""
        from apps.company.models import UserCompanyRole
        return self.has_any_role(company, [
            UserCompanyRole.OWNER,
            UserCompanyRole.PRODUCTION,
            UserCompanyRole.WORKER,
            UserCompanyRole.CLEANING,
        ])

    def can_view_planning(self, company):
        """Peut voir le planning (lecture seule pour WORKER)."""
        from apps.company.models import UserCompanyRole
        return self.has_any_role(company, [
            UserCompanyRole.OWNER,
            UserCompanyRole.PRODUCTION,
            UserCompanyRole.WORKER,
        ])

    def can_edit_planning(self, company):
        """Peut créer/modifier les plans de production."""
        from apps.company.models import UserCompanyRole
        return self.has_any_role(company, [
            UserCompanyRole.OWNER,
            UserCompanyRole.PRODUCTION,
        ])

    def can_import_sales(self, company):
        """Peut importer le CA et voir les prévisions."""
        from apps.company.models import UserCompanyRole
        return self.has_any_role(company, [UserCompanyRole.OWNER])
