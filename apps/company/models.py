from django.db import models
from apps.tenants.models import Tenant
from apps.users.models import User


class Company(models.Model):
    """
    Site physique (ex: Boulangerie Martin - Rue de la Paix).
    Un tenant peut avoir plusieurs sites.
    """
    class CompanyType(models.TextChoices):
        RESTAURANT = "REST", "Restaurant"
        BAKERY = "BAKE", "Boulangerie"
        BUTCHER = "BUTCH", "Boucherie"
        FISHMONGER = "FISH", "Poissonnerie"
        GROCERY = "GROC", "Épicerie"
        OTHER = "OTHER", "Autre"

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="companies")
    name = models.CharField(max_length=100, verbose_name="Raison sociale")
    company_type = models.CharField(
        max_length=5, choices=CompanyType.choices,
        default=CompanyType.RESTAURANT, verbose_name="Type"
    )
    address = models.CharField(max_length=120, blank=True, verbose_name="Adresse")
    zipcode = models.CharField(max_length=10, blank=True, verbose_name="Code postal")
    city = models.CharField(max_length=60, blank=True, verbose_name="Ville")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True, verbose_name="Email")
    siret = models.CharField(max_length=20, blank=True, verbose_name="SIRET")
    vat_number = models.CharField(max_length=20, blank=True, verbose_name="N° TVA")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site / Entreprise"
        verbose_name_plural = "Sites / Entreprises"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "siret"],
                name="unique_siret_per_tenant",
                condition=models.Q(siret__gt=""),  # uniquement si SIRET renseigné
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"


class StoragePlace(models.Model):
    """
    Lieu de stockage physique (frigo, congélateur, réserve sèche...).
    """
    TEMPERATURE_CHOICES = [
        ("frozen", "Surgelé < -18°C"),
        ("cold_1", "Réfrigéré 0-2°C"),
        ("cold_2", "Réfrigéré 0-4°C"),
        ("cold_3", "Frais 4-12°C"),
        ("dry", "Sec 15-20°C"),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="storage_places")
    name = models.CharField(max_length=60, verbose_name="Nom")
    temperature = models.CharField(
        max_length=10, choices=TEMPERATURE_CHOICES, verbose_name="Température"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Lieu de stockage"
        verbose_name_plural = "Lieux de stockage"
        ordering = ["company", "name"]

    def __str__(self):
        return f"{self.name} — {self.company.name}"


class Employee(models.Model):
    """
    Employé d'un site.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="employees")
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employee_profile"
    )
    first_name = models.CharField(max_length=60, verbose_name="Prénom")
    last_name = models.CharField(max_length=60, verbose_name="Nom")
    job_title = models.CharField(max_length=60, blank=True, verbose_name="Fonction")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True)
    hourly_cost = models.DecimalField(
        max_digits=6, decimal_places=2, default=0, verbose_name="Coût horaire"
    )
    weekly_hours = models.DecimalField(
        max_digits=5, decimal_places=2, default=35, verbose_name="Heures hebdo"
    )
    is_active = models.BooleanField(default=True, verbose_name="En activité")

    class Meta:
        verbose_name = "Employé"
        verbose_name_plural = "Employés"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Equipment(models.Model):
    """
    Équipement physique d'un site avec sa capacité par cycle.
    Ex: Pétrin 20kg, Moule 24 madeleines, Four 3 niveaux...
    """
    UNIT_CHOICES = [
        ("kg", "kg"),
        ("litre", "litre"),
        ("piece", "Pièce"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="equipment")
    name = models.CharField(max_length=100, verbose_name="Nom")
    description = models.CharField(max_length=200, blank=True, verbose_name="Description")
    capacity = models.DecimalField(
        max_digits=8, decimal_places=3,
        verbose_name="Capacité par cycle",
        help_text="Ex: 20 pour un pétrin de 20kg, 24 pour un moule de 24 madeleines"
    )
    capacity_unit = models.CharField(
        max_length=6, choices=UNIT_CHOICES, verbose_name="Unité de capacité"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Équipement"
        verbose_name_plural = "Équipements"
        ordering = ["company", "name"]

    def __str__(self):
        return f"{self.name} ({self.capacity} {self.capacity_unit}) — {self.company.name}"


class UserCompanyRole(models.Model):
    OWNER = "owner"
    PRODUCTION = "production"
    WORKER = "worker"
    CLEANING = "cleaning"
    ADMIN = "admin"

    ROLE_CHOICES = [
        (OWNER, "Patron / Gérant"),
        (PRODUCTION, "Chef de production"),
        (WORKER, "Ouvrier / Employé"),
        (CLEANING, "Agent d'entretien"),
        (ADMIN, "Administrateur"),
    ]

    PERMISSIONS = {
        ADMIN: {
            "manage_catalog", "view_financials", "manage_users",
            "record_production", "record_cleaning", "record_temperature",
            "view_planning", "edit_planning", "import_sales",
            "manage_reception", "manage_stock",
        },
        OWNER: {
            "manage_catalog", "view_financials", "manage_users",
            "record_production", "record_cleaning", "record_temperature",
            "view_planning", "edit_planning", "import_sales",
            "manage_reception", "manage_stock",
        },
        PRODUCTION: {
            "manage_catalog",
            "record_production", "record_cleaning", "record_temperature",
            "view_planning", "edit_planning",
            "manage_reception", "manage_stock",
        },
        WORKER: {
            "record_production", "record_cleaning", "record_temperature",
            "view_planning",
            "manage_reception", "manage_stock",
        },
        CLEANING: {
            "record_cleaning",
        },
    }

    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE,
        related_name="company_roles"
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE,
        related_name="user_roles"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name="Rôle")

    class Meta:
        verbose_name = "Rôle utilisateur / site"
        verbose_name_plural = "Rôles utilisateurs / sites"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "company", "role"],
                name="unique_user_company_role"
            )
        ]
        ordering = ["company", "role"]

    def __str__(self):
        return f"{self.user.username} — {self.get_role_display()} @ {self.company.name}"

    @classmethod
    def get_permissions_for_roles(cls, roles):
        perms = set()
        for role in roles:
            perms |= cls.PERMISSIONS.get(role, set())
        return perms