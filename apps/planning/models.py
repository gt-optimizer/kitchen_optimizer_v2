from decimal import Decimal
from django.db import models
from django.utils.timezone import now

from apps.company.models import Company
from apps.catalog.models import Recipe, Ingredient


class ProductionPlan(models.Model):
    """
    Plan de production — simulation avant de lancer la production réelle.

    Workflow :
      1. Créer un plan (brouillon)
      2. Ajouter des lignes (recettes + quantités)
      3. Calculer les besoins en ingrédients (IngredientNeed)
      4. Générer les bons de commande (PurchaseOrder)
      5. Valider le plan → devient un plan de production officiel
      6. Après production → statut 'done'

    Peut optionnellement s'appuyer sur les prévisions SalesForecast.
    """
    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("validated", "Validé"),
        ("done", "Réalisé"),
        ("cancelled", "Annulé"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="production_plans")
    name = models.CharField(max_length=100, verbose_name="Nom du plan")
    planned_date = models.DateField(verbose_name="Date de production prévue")
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES,
        default="draft", verbose_name="Statut"
    )
    use_forecast = models.BooleanField(
        default=False, verbose_name="Basé sur prévisions CA",
        help_text="Si activé, les quantités sont suggérées depuis SalesForecast"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plan de production"
        verbose_name_plural = "Plans de production"
        ordering = ["-planned_date"]

    def __str__(self):
        return f"{self.name} — {self.planned_date} ({self.get_status_display()})"

    def calculate_needs(self):
        """
        Déclenche le calcul des besoins en ingrédients pour ce plan.
        Supprime les anciens IngredientNeed et les recalcule.
        Appelé depuis le service needs_calculator.py.
        """
        self.ingredient_needs.all().delete()
        aggregated = {}  # {ingredient_id: {'quantity': Decimal, 'unit': str}}

        for line in self.lines.select_related("recipe"):
            self._aggregate_recipe(line.recipe, line.quantity, aggregated)

        for ingredient_id, data in aggregated.items():
            from apps.stock.models import StockLevel
            try:
                stock = StockLevel.objects.get(
                    company=self.company,
                    ingredient_id=ingredient_id
                ).quantity
            except StockLevel.DoesNotExist:
                stock = Decimal("0")

            to_order = max(Decimal("0"), data["quantity"] - stock)

            IngredientNeed.objects.create(
                plan=self,
                ingredient_id=ingredient_id,
                required_quantity=data["quantity"],
                available_stock=stock,
                to_order=to_order,
                unit=data["unit"],
            )

    def _aggregate_recipe(self, recipe, multiplier, aggregated):
        """
        Parcourt récursivement les lignes d'une recette
        et agrège les besoins en ingrédients.
        """
        for line in recipe.lines.select_related("ingredient", "sub_recipe"):
            qty = line.quantity * multiplier
            if line.ingredient:
                ing_id = line.ingredient_id
                if ing_id not in aggregated:
                    aggregated[ing_id] = {"quantity": Decimal("0"), "unit": line.unit}
                aggregated[ing_id]["quantity"] += qty
            elif line.sub_recipe:
                self._aggregate_recipe(line.sub_recipe, qty, aggregated)


class ProductionPlanLine(models.Model):
    """
    Ligne d'un plan de production — une recette avec sa quantité prévue.
    """
    plan = models.ForeignKey(ProductionPlan, on_delete=models.CASCADE, related_name="lines")
    recipe = models.ForeignKey(Recipe, on_delete=models.PROTECT, verbose_name="Recette")
    quantity = models.DecimalField(
        max_digits=10, decimal_places=3,
        verbose_name="Quantité prévue"
    )
    unit = models.CharField(max_length=10, verbose_name="Unité")
    notes = models.CharField(max_length=200, blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Ligne de plan"
        verbose_name_plural = "Lignes de plan"
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "recipe"],
                name="unique_recipe_per_plan"
            )
        ]

    def __str__(self):
        return f"{self.plan.name} — {self.recipe.name} × {self.quantity} {self.unit}"

    def cycles_detail(self):
        """
        Retourne le détail des cycles par équipement pour cette ligne.
        Ex: [{'equipment': 'Pétrin 20kg', 'cycles': 3, 'last_cycle_qty': 10}]
        """
        import math
        result = []
        for eq_line in self.recipe.equipment_lines.select_related("equipment"):
            if eq_line.batch_size and eq_line.batch_size > 0:
                cycles = math.ceil(float(self.quantity) / float(eq_line.batch_size))
                last_qty = float(self.quantity) % float(eq_line.batch_size)
                if last_qty == 0:
                    last_qty = float(eq_line.batch_size)
                result.append({
                    "equipment": str(eq_line.equipment),
                    "batch_size": eq_line.batch_size,
                    "batch_unit": eq_line.batch_unit,
                    "cycles": cycles,
                    "last_cycle_qty": round(last_qty, 3),
                    "step": str(eq_line.step) if eq_line.step else None,
                })
        return result


class IngredientNeed(models.Model):
    """
    Besoin calculé en ingrédient pour un plan de production.
    Généré par ProductionPlan.calculate_needs().

    required_quantity  = besoin total calculé récursivement
    available_stock    = stock disponible au moment du calcul
    to_order           = max(0, required - available)
    """
    plan = models.ForeignKey(
        ProductionPlan, on_delete=models.CASCADE, related_name="ingredient_needs"
    )
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, verbose_name="Ingrédient")
    required_quantity = models.DecimalField(
        max_digits=10, decimal_places=3, verbose_name="Quantité requise"
    )
    available_stock = models.DecimalField(
        max_digits=10, decimal_places=3, verbose_name="Stock disponible"
    )
    to_order = models.DecimalField(
        max_digits=10, decimal_places=3, verbose_name="Quantité à commander"
    )
    unit = models.CharField(max_length=10, verbose_name="Unité")

    class Meta:
        verbose_name = "Besoin en ingrédient"
        verbose_name_plural = "Besoins en ingrédients"
        ordering = ["ingredient__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "ingredient"],
                name="unique_ingredient_need_per_plan"
            )
        ]

    def __str__(self):
        return (
            f"{self.ingredient.name} — besoin: {self.required_quantity} "
            f"/ stock: {self.available_stock} / à commander: {self.to_order} {self.unit}"
        )


class PurchaseOrder(models.Model):
    """
    Bon de commande généré depuis un plan de production.
    Un bon de commande par fournisseur.
    """
    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("sent", "Envoyé"),
        ("received", "Reçu"),
    ]

    plan = models.ForeignKey(
        ProductionPlan, on_delete=models.CASCADE, related_name="purchase_orders"
    )
    supplier = models.ForeignKey(
        "purchasing.Supplier", on_delete=models.PROTECT, verbose_name="Fournisseur"
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES,
        default="draft", verbose_name="Statut"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Envoyé le")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Bon de commande"
        verbose_name_plural = "Bons de commande"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "supplier"],
                name="unique_order_per_plan_supplier"
            )
        ]

    def __str__(self):
        return f"BC {self.supplier.name} — {self.plan.name} ({self.get_status_display()})"

    @property
    def total_amount(self):
        from django.db.models import Sum, F, ExpressionWrapper, DecimalField
        result = self.lines.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("quantity") * F("unit_price"),
                    output_field=DecimalField()
                )
            )
        )
        return result["total"] or Decimal("0")


class PurchaseOrderLine(models.Model):
    """
    Ligne d'un bon de commande.
    Prix unitaire pré-rempli depuis SupplierIngredient.negotiated_price.
    """
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, verbose_name="Ingrédient")
    supplier_ref = models.ForeignKey(
        "purchasing.SupplierIngredient", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Référence fournisseur"
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Quantité")
    unit = models.CharField(max_length=10, verbose_name="Unité")
    unit_price = models.DecimalField(
        max_digits=9, decimal_places=4, default=0,
        verbose_name="Prix unitaire HT"
    )
    notes = models.CharField(max_length=200, blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"

    def __str__(self):
        return f"{self.ingredient.name} × {self.quantity} {self.unit} @ {self.unit_price}€"

    @property
    def line_total(self):
        return round(self.quantity * self.unit_price, 2)