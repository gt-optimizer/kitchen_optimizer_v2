from datetime import timedelta
from django.db import models
from django.utils.timezone import now

from apps.company.models import Company
from apps.catalog.models import Recipe
from apps.purchasing.models import ReceptionLine


class ProductionBatch(models.Model):
    """
    Lot de production — regroupe plusieurs recettes produites le même jour.
    Sert de base à la traçabilité.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="production_batches")
    date = models.DateField(default=now, verbose_name="Date de production")
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lot de production"
        verbose_name_plural = "Lots de production"
        ordering = ["-date"]

    def __str__(self):
        return f"Lot n°{self.pk} — {self.company.name} ({self.date})"


class ProductionRecord(models.Model):
    """
    Enregistrement de production d'une recette dans un lot.
    Ex: 3 entremets 60x40 produits le 24/02/2026.
    """
    batch = models.ForeignKey(ProductionBatch, on_delete=models.CASCADE, related_name="records")
    recipe = models.ForeignKey(Recipe, on_delete=models.PROTECT, verbose_name="Recette")
    quantity = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Quantité produite")
    best_before = models.DateField(null=True, blank=True, verbose_name="DLC / DLUO")
    opening_date = models.DateField(null=True, blank=True, verbose_name="Date d'ouverture")
    in_stock = models.BooleanField(default=True, verbose_name="En stock")

    class Meta:
        verbose_name = "Enregistrement de production"
        verbose_name_plural = "Enregistrements de production"

    def __str__(self):
        return f"{self.recipe.name} × {self.quantity} ({self.batch})"

    @property
    def computed_best_before(self):
        """
        DLC calculée dynamiquement :
        - Si ouvert → date ouverture + DLC après ouverture
        - Sinon   → date production + DLC standard
        """
        if self.opening_date:
            return self.opening_date + timedelta(days=self.recipe.shelf_life_after_opening_days)
        return self.batch.date + timedelta(days=self.recipe.shelf_life_days)

    def save(self, *args, **kwargs):
        self.best_before = self.computed_best_before
        super().save(*args, **kwargs)


class Traceability(models.Model):
    """
    Lien entre un enregistrement de production et les lots de réception utilisés.
    Répond à la question : "Quel lot de chocolat a été utilisé pour cet entremet ?"
    """
    production_record = models.ForeignKey(
        ProductionRecord, on_delete=models.CASCADE, related_name="traceability_lines"
    )
    reception_line = models.ForeignKey(
        ReceptionLine, on_delete=models.PROTECT,
        verbose_name="Lot reçu utilisé",
        limit_choices_to={"batch_on_site": True}
    )
    quantity_used = models.DecimalField(
        max_digits=8, decimal_places=3,
        verbose_name="Quantité utilisée"
    )

    class Meta:
        verbose_name = "Traçabilité"
        verbose_name_plural = "Traçabilités"

    def __str__(self):
        return (
            f"{self.production_record.recipe.name} ← "
            f"{self.reception_line.ingredient.name} "
            f"lot {self.reception_line.tracability_number}"
        )