from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError

from apps.tenants.models import Tenant
from apps.utilities.models import VatRate


class PriceRecord(models.Model):
    """
    Enregistrement de prix — achat (Ingredient) ou vente (Recipe).

    Règle métier :
        purchase  → price_ht saisi, price_ttc = None, pas de TVA
        retail    → price_ttc saisi, price_ht calculé et stocké, TVA obligatoire
        wholesale → price_ttc saisi, price_ht calculé et stocké, TVA obligatoire

    Le coût de revient interne (production) est une property calculée
    sur Ingredient.cost_per_kg et Recipe.cost_per_unit — pas stocké ici.
    """

    CHANNEL_CHOICES = [
        ("purchase",  "Achat fournisseur"),
        ("retail",    "Vente détail"),
        ("wholesale", "Vente en gros"),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name="price_records"
    )

    # ── Cible : Ingredient XOR Recipe ─────────────────────────────────────────
    ingredient = models.ForeignKey(
        "catalog.Ingredient",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="price_records",
        verbose_name="Ingrédient"
    )
    recipe = models.ForeignKey(
        "catalog.Recipe",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="price_records",
        verbose_name="Recette"
    )

    # ── Canal & Prix ──────────────────────────────────────────────────────────
    SOURCE_CHOICES = [
        ("manual", "Saisie manuelle"),
        ("ocr_bl", "OCR bon de livraison"),
        ("ocr_invoice", "OCR facture"),
        ("import", "Import fichier"),
    ]
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES,
        default="manual", verbose_name="Source"
    )
    channel = models.CharField(
        max_length=20, choices=CHANNEL_CHOICES,
        verbose_name="Canal"
    )
    price_ht = models.DecimalField(
        max_digits=10, decimal_places=4,
        null=True, blank=True,
        verbose_name="Prix HT (€)"
    )
    price_ttc = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Prix TTC (€)"
    )
    vat_rate = models.ForeignKey(
        VatRate, on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name="Taux de TVA"
    )

    # ── Validité ──────────────────────────────────────────────────────────────
    valid_from = models.DateField(verbose_name="Valide à partir du")
    valid_until = models.DateField(
        null=True, blank=True,
        verbose_name="Valide jusqu'au",
        help_text="Laisser vide = prix courant actif"
    )

    notes = models.CharField(max_length=300, blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Enregistrement de prix"
        verbose_name_plural = "Enregistrements de prix"
        ordering = ["-valid_from"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(ingredient__isnull=False, recipe__isnull=True) |
                    models.Q(ingredient__isnull=True,  recipe__isnull=False)
                ),
                name="pricerecord_ingredient_xor_recipe",
                violation_error_message="Un PriceRecord doit être lié à un ingrédient OU une recette, pas les deux."
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(channel="purchase") |
                    models.Q(ingredient__isnull=False)
                ),
                name="pricerecord_purchase_only_for_ingredient",
                violation_error_message="Le canal 'purchase' est réservé aux ingrédients."
            ),
        ]

    def clean(self):
        # XOR uniquement si les deux sont renseignés simultanément
        if self.ingredient and self.recipe:
            raise ValidationError("Un PriceRecord ne peut pas être lié à la fois à un ingrédient et une recette.")

        # Cohérence canal / prix
        if self.channel == "purchase":
            if not self.price_ht:
                raise ValidationError("Un prix d'achat nécessite un prix HT.")
            if self.vat_rate:
                raise ValidationError("Un prix d'achat ne doit pas avoir de TVA.")
        elif self.channel in ("retail", "wholesale"):
            if not self.price_ttc:
                raise ValidationError("Un prix de vente nécessite un prix TTC.")
            if not self.vat_rate:
                raise ValidationError("Un prix de vente nécessite un taux de TVA.")

        # Cohérence dates
        if self.valid_until and self.valid_from and self.valid_until < self.valid_from:
            raise ValidationError("La date de fin doit être postérieure à la date de début.")

    def save(self, *args, **kwargs):
        """Calcule le prix manquant avant sauvegarde."""
        if self.channel in ("retail", "wholesale"):
            if self.price_ttc and self.vat_rate:
                self.price_ht = round(
                    self.price_ttc / (1 + self.vat_rate.rate), 4
                )
        elif self.channel == "purchase":
            self.price_ttc = None
        super().save(*args, **kwargs)

    def __str__(self):
        target = self.ingredient or self.recipe
        return f"{target} — {self.get_channel_display()} — {self.price_ht}€ HT ({self.valid_from})"

    @property
    def is_current(self) -> bool:
        """True si ce prix est actif aujourd'hui."""
        from django.utils import timezone
        today = timezone.localdate()
        if self.valid_from > today:
            return False
        if self.valid_until and self.valid_until < today:
            return False
        return True