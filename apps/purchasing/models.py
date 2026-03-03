from django.db import models
from django.db.models import Sum
from django.utils.timezone import now

from apps.tenants.models import Tenant
from apps.company.models import Company, StoragePlace
from apps.catalog.models import Ingredient


class Supplier(models.Model):
    """
    Fournisseur — partagé entre tous les sites d'un tenant.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="suppliers")
    name = models.CharField(max_length=100, verbose_name="Raison sociale")
    address = models.CharField(max_length=120, blank=True, verbose_name="Adresse")
    zipcode = models.CharField(max_length=10, blank=True, verbose_name="Code postal")
    city = models.CharField(max_length=60, blank=True, verbose_name="Ville")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True)
    rcs = models.CharField(max_length=60, blank=True, verbose_name="N° RCS")
    siret = models.CharField(max_length=20, blank=True, verbose_name="N° SIRET")
    vat_number = models.CharField(max_length=20, blank=True, verbose_name="N° TVA")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_supplier_per_tenant")
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class SupplierContact(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="contacts")
    first_name = models.CharField(max_length=60, verbose_name="Prénom")
    last_name = models.CharField(max_length=60, verbose_name="Nom")
    job_title = models.CharField(max_length=60, blank=True, verbose_name="Fonction")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    mobile = models.CharField(max_length=20, blank=True, verbose_name="Mobile")
    email = models.EmailField(blank=True)

    class Meta:
        verbose_name = "Contact fournisseur"
        verbose_name_plural = "Contacts fournisseurs"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.supplier.name})"


class SupplierIngredient(models.Model):
    """
    Référence fournisseur pour un ingrédient.
    Un ingrédient peut avoir plusieurs références fournisseurs.
    Ex: Chocolat 70% → Valrhona ref. XA123 ET Barry ref. CB456
    """
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="supplier_ingredients")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="supplier_refs")
    supplier_item_number = models.CharField(max_length=40, blank=True, verbose_name="Référence fournisseur")
    supplier_item_name = models.CharField(max_length=100, blank=True, verbose_name="Désignation fournisseur")
    ean13 = models.CharField(max_length=13, blank=True, verbose_name="EAN13")
    negotiated_price = models.DecimalField(
        max_digits=9, decimal_places=4, default=0,
        verbose_name="Prix négocié HT"
    )
    is_preferred = models.BooleanField(default=False, verbose_name="Fournisseur préféré")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Référence fournisseur"
        verbose_name_plural = "Références fournisseurs"
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "ingredient"],
                name="unique_supplier_ingredient"
            )
        ]

    def __str__(self):
        return f"{self.ingredient.name} — {self.supplier.name}"


class CompanyIngredient(models.Model):
    """
    Configuration locale d'un ingrédient pour un site précis.
    Lieu de stockage, stock minimum — spécifiques au site.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="ingredient_configs")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="company_configs")
    storage_place = models.ForeignKey(
        StoragePlace, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Lieu de stockage"
    )
    storage_reference = models.CharField(max_length=20, blank=True, verbose_name="Emplacement")
    minimum_stock = models.DecimalField(
        max_digits=8, decimal_places=3, default=0,
        verbose_name="Stock minimum"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Configuration ingrédient / site"
        verbose_name_plural = "Configurations ingrédients / sites"
        constraints = [
            models.UniqueConstraint(fields=["company", "ingredient"], name="unique_company_ingredient")
        ]

    def __str__(self):
        return f"{self.ingredient.name} @ {self.company.name}"


class Reception(models.Model):
    """
    Bon de réception — en-tête.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="receptions")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, verbose_name="Fournisseur")
    reception_number = models.CharField(max_length=30, unique=True, blank=True, verbose_name="N° réception")
    delivery_date = models.DateField(default=now, verbose_name="Date de livraison")
    invoice_number = models.CharField(max_length=60, blank=True, verbose_name="N° facture")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Réception"
        verbose_name_plural = "Réceptions"
        ordering = ["-delivery_date"]

    def __str__(self):
        return f"{self.reception_number} — {self.supplier.name} ({self.delivery_date})"

    @property
    def total_amount(self):
        return self.lines.aggregate(total=Sum("invoiced_amount"))["total"] or 0

    def save(self, *args, **kwargs):
        if not self.reception_number:
            date_str = self.delivery_date.strftime("%Y-%m-%d")
            last = Reception.objects.filter(
                delivery_date=self.delivery_date
            ).order_by("reception_number").last()

            if last and last.reception_number:
                try:
                    last_num = int(last.reception_number.split("-n°")[-1])
                except (ValueError, IndexError):
                    last_num = 0
            else:
                last_num = 0

            self.reception_number = f"{date_str}-n°{last_num + 1:03d}"
        super().save(*args, **kwargs)


class ReceptionLine(models.Model):
    """
    Ligne de réception — détail par ingrédient.
    """
    reception = models.ForeignKey(Reception, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT,
        verbose_name="Ingrédient"
    )
    supplier_ref = models.ForeignKey(
        SupplierIngredient, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Référence fournisseur"
    )
    tracability_number = models.CharField(max_length=60, blank=True, verbose_name="N° de lot")
    best_before = models.DateField(null=True, blank=True, verbose_name="DLC / DLUO")
    invoiced_quantity = models.DecimalField(
        max_digits=9, decimal_places=3, verbose_name="Quantité facturée"
    )
    invoiced_price = models.DecimalField(
        max_digits=9, decimal_places=4, verbose_name="Prix unitaire HT"
    )
    invoiced_amount = models.DecimalField(
        max_digits=10, decimal_places=3, editable=False,
        verbose_name="Montant HT"
    )
    batch_on_site = models.BooleanField(default=True, verbose_name="Lot présent")

    class Meta:
        verbose_name = "Ligne de réception"
        verbose_name_plural = "Lignes de réception"

    def __str__(self):
        return f"{self.ingredient.name} — {self.reception}"

    def save(self, *args, **kwargs):
        # Calcul automatique du montant
        self.invoiced_amount = round(
            (self.invoiced_price or 0) * (self.invoiced_quantity or 0), 3
        )
        # Mise à jour du prix de référence sur l'ingrédient
        if self.invoiced_price and self.ingredient_id:
            Ingredient.objects.filter(pk=self.ingredient_id).update(
                reference_price=self.invoiced_price
            )
        super().save(*args, **kwargs)


class DeliveryDocument(models.Model):
    """
    PDF ou image d'un BL/facture uploadé par l'utilisateur.
    Cycle de vie : upload → OCR → parsing → validation → application prix
    """
    STATUS_CHOICES = [
        ("pending",   "En attente de traitement"),
        ("parsing",   "OCR en cours..."),
        ("parsed",    "Analysé — en attente de validation"),
        ("validated", "Validé — prix appliqués"),
        ("error",     "Erreur OCR"),
    ]
    DOC_TYPE_CHOICES = [
        ("bl",      "Bon de livraison"),
        ("invoice", "Facture"),
        ("other",   "Autre document"),
    ]

    tenant        = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="delivery_documents")
    supplier      = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    document      = models.FileField(upload_to="purchasing/documents/", verbose_name="Document")
    document_type = models.CharField(max_length=10, choices=DOC_TYPE_CHOICES, default="other", verbose_name="Type")
    document_date = models.DateField(null=True, blank=True, verbose_name="Date du document")
    reference     = models.CharField(max_length=60, blank=True, verbose_name="N° BL / Facture")
    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    ocr_raw       = models.JSONField(default=dict, blank=True, verbose_name="Résultat OCR brut")
    ocr_engine    = models.CharField(max_length=20, blank=True, verbose_name="Moteur OCR utilisé")
    notes         = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Document de livraison"
        verbose_name_plural = "Documents de livraison"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_document_type_display()} — {self.supplier} — {self.document_date or self.created_at.date()}"


class DeliveryLine(models.Model):
    """
    Ligne extraite du document par OCR — avant validation.
    Peut être un produit, une taxe filière, une remise ou des frais de port.
    """
    LINE_TYPE_CHOICES = [
        ("product",    "Produit"),
        ("sector_tax", "Taxe filière"),
        ("discount",   "Remise"),
        ("shipping",   "Frais de port"),
        ("other",      "Autre"),
    ]

    # Codes de taxes filière viande connus
    SECTOR_TAX_CODES = [
        "CVO", "INAPORC", "INTERBEV", "IP3", "IP3V", "IP5", "RSD", "TEO"
    ]

    document       = models.ForeignKey(DeliveryDocument, on_delete=models.CASCADE, related_name="lines")
    line_type      = models.CharField(max_length=12, choices=LINE_TYPE_CHOICES, default="product")
    order          = models.PositiveSmallIntegerField(default=0)

    # Données extraites par OCR
    raw_label      = models.CharField(max_length=300, verbose_name="Libellé brut OCR")
    quantity       = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    unit           = models.CharField(max_length=20, blank=True)
    unit_price_ht  = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, verbose_name="PU HT")
    total_ht       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Total HT")

    # Matching ingrédient (fuzzy)
    matched_ingredient = models.ForeignKey(
        Ingredient, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="delivery_lines",
        verbose_name="Ingrédient associé"
    )
    match_score    = models.FloatField(null=True, blank=True, verbose_name="Score matching (0-100)")
    match_confirmed = models.BooleanField(default=False, verbose_name="Matching confirmé")

    # Taxes filière
    tax_code       = models.CharField(max_length=20, blank=True, verbose_name="Code taxe")

    # Après validation
    applied        = models.BooleanField(default=False, verbose_name="Prix appliqué")
    reception_line = models.OneToOneField(
        "ReceptionLine", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="delivery_line"
    )

    class Meta:
        verbose_name = "Ligne document"
        verbose_name_plural = "Lignes document"
        ordering = ["order"]

    def __str__(self):
        return f"{self.raw_label} — {self.get_line_type_display()}"

    @property
    def is_sector_tax(self):
        return self.line_type == "sector_tax"