from decimal import Decimal
from django.db import models
from django.utils.timezone import now

from apps.company.models import Company
from apps.catalog.models import Ingredient


class StockLevel(models.Model):
    """
    Niveau de stock actuel par ingrédient par site.
    Mis à jour à chaque StockMovement via signal.
    Une seule ligne par (company, ingredient).
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stock_levels")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="stock_levels")
    quantity = models.DecimalField(
        max_digits=10, decimal_places=3, default=0,
        verbose_name="Quantité en stock"
    )
    unit = models.CharField(max_length=10, verbose_name="Unité")
    last_updated = models.DateTimeField(auto_now=True, verbose_name="Dernière mise à jour")

    class Meta:
        verbose_name = "Niveau de stock"
        verbose_name_plural = "Niveaux de stock"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "ingredient"],
                name="unique_stock_level_per_company_ingredient"
            )
        ]
        ordering = ["ingredient__name"]

    def __str__(self):
        return f"{self.ingredient.name} @ {self.company.name} : {self.quantity} {self.unit}"

    @property
    def is_below_minimum(self):
        """True si le stock est sous le seuil minimum configuré."""
        from apps.purchasing.models import CompanyIngredient
        try:
            config = CompanyIngredient.objects.get(
                company=self.company, ingredient=self.ingredient
            )
            return self.quantity < config.minimum_stock
        except CompanyIngredient.DoesNotExist:
            return False

    @property
    def minimum_stock(self):
        from apps.purchasing.models import CompanyIngredient
        try:
            return CompanyIngredient.objects.get(
                company=self.company, ingredient=self.ingredient
            ).minimum_stock
        except CompanyIngredient.DoesNotExist:
            return Decimal("0")


class StockMovement(models.Model):
    """
    Mouvement de stock — toute entrée ou sortie est tracée ici.
    Le StockLevel est recalculé après chaque mouvement via signal.

    Types :
      reception     → entrée  (depuis ReceptionLine)
      production    → sortie  (depuis ProductionRecord, consommation matières)
      production_in → entrée  (depuis ProductionRecord, produit fini en stock)
      correction    → +/- manuel (perte, casse, don...)
      transfer_out  → sortie  (depuis InternalTransferLine)
      transfer_in   → entrée  (depuis InternalTransferLine)
      inventory     → correction suite à inventaire
    """
    MOVEMENT_TYPES = [
        ("reception", "Réception fournisseur"),
        ("production", "Consommation production"),
        ("production_in", "Entrée production (produit fini)"),
        ("correction", "Correction manuelle"),
        ("transfer_out", "Transfert sortant"),
        ("transfer_in", "Transfert entrant"),
        ("inventory", "Correction inventaire"),
    ]

    CORRECTION_REASONS = [
        ("waste", "Perte / jet"),
        ("expired", "Périmé"),
        ("damaged", "Abîmé / cassé"),
        ("gift", "Don"),
        ("theft", "Vol"),
        ("other", "Autre"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stock_movements")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES, verbose_name="Type")
    quantity = models.DecimalField(
        max_digits=10, decimal_places=3,
        verbose_name="Quantité",
        help_text="Positif = entrée, Négatif = sortie"
    )
    unit = models.CharField(max_length=10, verbose_name="Unité")
    moved_at = models.DateTimeField(default=now, verbose_name="Date / heure")

    # Raison (pour les corrections uniquement)
    correction_reason = models.CharField(
        max_length=20, choices=CORRECTION_REASONS,
        blank=True, verbose_name="Raison de correction"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    # Liens vers l'origine du mouvement (un seul renseigné à la fois)
    reception_line = models.ForeignKey(
        "purchasing.ReceptionLine", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_movements"
    )
    production_record = models.ForeignKey(
        "production.ProductionRecord", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_movements"
    )
    transfer_line = models.ForeignKey(
        "pms.InternalTransferLine", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_movements"
    )
    inventory_line = models.ForeignKey(
        "stock.InventoryLine", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_movements"
    )

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ["-moved_at"]

    def __str__(self):
        sign = "+" if self.quantity >= 0 else ""
        return (
            f"{self.ingredient.name} {sign}{self.quantity} {self.unit} "
            f"({self.get_movement_type_display()}) — {self.moved_at:%d/%m/%Y %H:%M}"
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Mise à jour du StockLevel après chaque mouvement
        stock_level, _ = StockLevel.objects.get_or_create(
            company=self.company,
            ingredient=self.ingredient,
            defaults={"unit": self.unit, "quantity": Decimal("0")}
        )
        stock_level.quantity = models.F("quantity") + self.quantity
        stock_level.save(update_fields=["quantity", "last_updated"])


class Inventory(models.Model):
    """
    Session d'inventaire — regroupe toutes les lignes comptées.
    Interface : mobile/tablette (on est dans la réserve).
    """
    STATUS_CHOICES = [
        ("draft", "En cours"),
        ("validated", "Validé"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="inventories")
    started_at = models.DateTimeField(default=now, verbose_name="Début inventaire")
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES,
        default="draft", verbose_name="Statut"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Inventaire"
        verbose_name_plural = "Inventaires"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Inventaire {self.company.name} — {self.started_at:%d/%m/%Y} ({self.get_status_display()})"

    def validate(self):
        """
        Valide l'inventaire :
        - Crée un StockMovement de type 'inventory' pour chaque écart
        - Passe le statut à 'validated'
        """
        from django.utils.timezone import now as tz_now
        for line in self.lines.all():
            delta = line.counted_quantity - line.theoretical_quantity
            if delta != 0:
                StockMovement.objects.create(
                    company=self.company,
                    ingredient=line.ingredient,
                    movement_type="inventory",
                    quantity=delta,
                    unit=line.unit,
                    notes=f"Correction inventaire du {self.started_at:%d/%m/%Y}",
                    inventory_line=line,
                )
        self.status = "validated"
        self.validated_at = tz_now()
        self.save(update_fields=["status", "validated_at"])


class InventoryLine(models.Model):
    """
    Ligne d'inventaire — une ligne par ingrédient compté.
    theoretical_quantity est calculé depuis StockLevel au moment de la création.
    """
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, verbose_name="Ingrédient")
    unit = models.CharField(max_length=10, verbose_name="Unité")
    theoretical_quantity = models.DecimalField(
        max_digits=10, decimal_places=3,
        verbose_name="Quantité théorique (stock calculé)"
    )
    counted_quantity = models.DecimalField(
        max_digits=10, decimal_places=3,
        verbose_name="Quantité comptée"
    )
    notes = models.CharField(max_length=200, blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Ligne d'inventaire"
        verbose_name_plural = "Lignes d'inventaire"
        constraints = [
            models.UniqueConstraint(
                fields=["inventory", "ingredient"],
                name="unique_ingredient_per_inventory"
            )
        ]

    def __str__(self):
        return f"{self.ingredient.name} — théorique: {self.theoretical_quantity} / compté: {self.counted_quantity}"

    @property
    def delta(self):
        """Écart entre compté et théorique."""
        return round(self.counted_quantity - self.theoretical_quantity, 3)

    @property
    def is_compliant(self):
        return self.delta == 0