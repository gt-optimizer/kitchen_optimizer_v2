"""
App stock — gestion des stocks par lot (StockBatch), niveau agrégé (StockLevel),
mouvements (StockMovement), inventaires (Inventory / InventoryLine).

Supporte :
  - Ingrédients bruts ET recettes produites (produits finis / semi-finis)
  - Gestion au lot avec FIFO guidé
  - DLC (bloquant) / DLUO (avertissement) / Sans date
  - Transferts inter-sites
  - Inventaires avec correction automatique
"""
from decimal import Decimal
from django.db import models
from django.utils.timezone import now

from apps.company.models import Company, StoragePlace
from apps.catalog.models import Ingredient, Recipe


# ── Helpers ────────────────────────────────────────────────────────────────────

def _stock_item_check():
    """CheckConstraint réutilisable : ingredient XOR recipe."""
    return models.CheckConstraint(
        check=(
            models.Q(ingredient__isnull=False, recipe__isnull=True) |
            models.Q(ingredient__isnull=True, recipe__isnull=False)
        ),
        name="%(class)s_ingredient_xor_recipe",
        violation_error_message="Un article de stock doit être soit un ingrédient, soit une recette — pas les deux, pas aucun."
    )


# ── StockBatch ─────────────────────────────────────────────────────────────────

class StockBatch(models.Model):
    """
    Lot physique en stock.
    Représente une quantité homogène d'un article (même DLC, même n° lot).

    Cycle de vie :
      - Créé à la réception d'un ingrédient (via ReceptionLine)
      - Créé à la production d'une recette (via ProductionRecord)
      - Décrémenté à chaque sortie (production, vente, correction)
      - Épuisé quand quantity_remaining = 0

    FIFO : tri par best_before ASC, puis created_at ASC.
    """
    DATE_TYPE_CHOICES = [
        ("dlc",  "DLC — Date Limite de Consommation (bloquant)"),
        ("dluo", "DLUO — Date Limite d'Utilisation Optimale (avertissement)"),
        ("none", "Sans date limite"),
    ]

    company    = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stock_batches")
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE,
        null=True, blank=True, related_name="stock_batches"
    )
    recipe     = models.ForeignKey(
        Recipe, on_delete=models.CASCADE,
        null=True, blank=True, related_name="stock_batches"
    )

    # Origine
    reception_line    = models.ForeignKey(
        "purchasing.ReceptionLine", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_batches"
    )
    production_record = models.ForeignKey(
        "production.ProductionRecord", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_batches"
    )

    # Quantité
    quantity_initial   = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Quantité initiale")
    quantity_remaining = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Quantité restante")
    unit               = models.CharField(max_length=10, verbose_name="Unité")

    # Traçabilité & DLC
    tracability_number = models.CharField(max_length=60, blank=True, verbose_name="N° de lot")
    best_before        = models.DateField(null=True, blank=True, verbose_name="DLC / DLUO")
    date_type          = models.CharField(
        max_length=4, choices=DATE_TYPE_CHOICES,
        default="dluo", verbose_name="Type de date limite"
    )

    # Stockage
    storage_place = models.ForeignKey(
        StoragePlace, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Lieu de stockage"
    )

    # Prix au moment de l'entrée en stock (figé)
    unit_price_at_entry = models.DecimalField(
        max_digits=9, decimal_places=4, default=0,
        verbose_name="Prix unitaire HT (à l'entrée)"
    )

    created_at  = models.DateTimeField(auto_now_add=True)
    is_depleted = models.BooleanField(default=False, verbose_name="Épuisé", db_index=True)

    class Meta:
        verbose_name = "Lot en stock"
        verbose_name_plural = "Lots en stock"
        ordering = ["best_before", "created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(ingredient__isnull=False, recipe__isnull=True) |
                    models.Q(ingredient__isnull=True, recipe__isnull=False)
                ),
                name="stockbatch_ingredient_xor_recipe",
            )
        ]

    def __str__(self):
        article = self.ingredient or self.recipe
        dlc = f" — {self.best_before}" if self.best_before else ""
        return f"{article} × {self.quantity_remaining} {self.unit}{dlc}"

    @property
    def article(self):
        """Retourne l'ingrédient ou la recette."""
        return self.ingredient or self.recipe

    @property
    def article_name(self):
        return self.article.name if self.article else "—"

    @property
    def is_expired(self):
        """True si la DLC/DLUO est dépassée."""
        if self.best_before:
            from django.utils.timezone import localdate
            return localdate() > self.best_before
        return False

    @property
    def is_dlc_warning(self):
        """True si DLC dans moins de 3 jours."""
        if self.best_before and not self.is_expired:
            from django.utils.timezone import localdate
            from datetime import timedelta
            return self.best_before <= localdate() + timedelta(days=3)
        return False

    @property
    def value_remaining(self):
        """Valeur restante du lot (quantité × prix entrée)."""
        return round(self.quantity_remaining * self.unit_price_at_entry, 4)

    def consume(self, quantity):
        """
        Consomme une quantité du lot.
        Lève ValueError si quantité insuffisante.
        """
        if quantity > self.quantity_remaining:
            raise ValueError(
                f"Stock insuffisant sur lot {self.pk} : "
                f"demandé {quantity}, disponible {self.quantity_remaining}"
            )
        self.quantity_remaining -= quantity
        if self.quantity_remaining == 0:
            self.is_depleted = True
        self.save(update_fields=["quantity_remaining", "is_depleted"])

    @classmethod
    def get_fifo_batches(cls, company, ingredient=None, recipe=None):
        """
        Retourne les lots disponibles triés FIFO (DLC la plus proche en premier).
        Exclut les lots épuisés et les DLC dépassées et bloquantes.
        """
        from django.utils.timezone import localdate
        qs = cls.objects.filter(
            company=company,
            is_depleted=False,
        )
        if ingredient:
            qs = qs.filter(ingredient=ingredient)
        elif recipe:
            qs = qs.filter(recipe=recipe)

        # Exclure les lots DLC bloquants périmés
        today = localdate()
        qs = qs.exclude(
            date_type="dlc",
            best_before__lt=today,
        )
        return qs.select_related("ingredient", "recipe", "storage_place").order_by(
            "best_before", "created_at"
        )

    @classmethod
    def compute_date_type(cls, shelf_life_days):
        """
        Détermine automatiquement le type de date limite
        en fonction de la durée de conservation.
        - Pas de DLC définie → none
        - <= 7 jours → DLC (bloquant, produit frais)
        - > 7 jours → DLUO (avertissement)
        """
        if not shelf_life_days or shelf_life_days == 0:
            return "none"
        if shelf_life_days <= 7:
            return "dlc"
        return "dluo"


# ── StockLevel ─────────────────────────────────────────────────────────────────

class StockLevel(models.Model):
    """
    Niveau de stock agrégé par article par site.
    Mis à jour à chaque StockMovement via signal.
    Ne jamais modifier directement — passer par StockMovement.
    """
    company    = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stock_levels")
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE,
        null=True, blank=True, related_name="stock_levels"
    )
    recipe     = models.ForeignKey(
        Recipe, on_delete=models.CASCADE,
        null=True, blank=True, related_name="stock_levels"
    )
    quantity     = models.DecimalField(max_digits=10, decimal_places=3, default=0, verbose_name="Quantité en stock")
    unit         = models.CharField(max_length=10, verbose_name="Unité")
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Niveau de stock"
        verbose_name_plural = "Niveaux de stock"
        ordering = []
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(ingredient__isnull=False, recipe__isnull=True) |
                    models.Q(ingredient__isnull=True, recipe__isnull=False)
                ),
                name="stocklevel_ingredient_xor_recipe",
            ),
            models.UniqueConstraint(
                fields=["company", "ingredient"],
                condition=models.Q(ingredient__isnull=False),
                name="unique_stock_level_ingredient",
            ),
            models.UniqueConstraint(
                fields=["company", "recipe"],
                condition=models.Q(recipe__isnull=False),
                name="unique_stock_level_recipe",
            ),
        ]

    def __str__(self):
        article = self.ingredient or self.recipe
        return f"{article} @ {self.company.name} : {self.quantity} {self.unit}"

    @property
    def article(self):
        return self.ingredient or self.recipe

    @property
    def article_name(self):
        return self.article.name if self.article else "—"

    @property
    def is_below_minimum(self):
        """True si le stock est sous le seuil minimum configuré (ingrédients uniquement)."""
        if not self.ingredient:
            return False
        from apps.purchasing.models import CompanyIngredient
        try:
            config = CompanyIngredient.objects.get(
                company=self.company, ingredient=self.ingredient
            )
            return config.minimum_stock > 0 and self.quantity < config.minimum_stock
        except CompanyIngredient.DoesNotExist:
            return False

    @property
    def minimum_stock(self):
        if not self.ingredient:
            return Decimal("0")
        from apps.purchasing.models import CompanyIngredient
        try:
            return CompanyIngredient.objects.get(
                company=self.company, ingredient=self.ingredient
            ).minimum_stock
        except CompanyIngredient.DoesNotExist:
            return Decimal("0")


# ── StockMovement ──────────────────────────────────────────────────────────────

class StockMovement(models.Model):
    """
    Mouvement de stock — toute entrée ou sortie tracée ici.
    Le StockLevel est recalculé après chaque mouvement.
    quantity > 0 = entrée, quantity < 0 = sortie.
    """
    MOVEMENT_TYPES = [
        ("reception",     "Réception fournisseur"),
        ("production",    "Consommation production"),
        ("production_in", "Entrée production (produit fini)"),
        ("correction",    "Correction manuelle"),
        ("transfer_out",  "Transfert sortant"),
        ("transfer_in",   "Transfert entrant"),
        ("inventory",     "Correction inventaire"),
    ]

    CORRECTION_REASONS = [
        ("waste",    "Perte / jet"),
        ("expired",  "Périmé"),
        ("damaged",  "Abîmé / cassé"),
        ("gift",     "Don"),
        ("theft",    "Vol"),
        ("other",    "Autre"),
    ]

    company    = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stock_movements")
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE,
        null=True, blank=True, related_name="stock_movements"
    )
    recipe     = models.ForeignKey(
        Recipe, on_delete=models.CASCADE,
        null=True, blank=True, related_name="stock_movements"
    )

    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES, verbose_name="Type")
    quantity      = models.DecimalField(
        max_digits=10, decimal_places=3,
        verbose_name="Quantité",
        help_text="Positif = entrée, Négatif = sortie"
    )
    unit     = models.CharField(max_length=10, verbose_name="Unité")
    moved_at = models.DateTimeField(default=now, verbose_name="Date / heure")

    # Lot concerné (optionnel — pour traçabilité fine)
    stock_batch = models.ForeignKey(
        StockBatch, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="movements",
        verbose_name="Lot concerné"
    )

    # Raison correction
    correction_reason = models.CharField(
        max_length=20, choices=CORRECTION_REASONS,
        blank=True, verbose_name="Raison de correction"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    # Liens origine (un seul renseigné à la fois)
    reception_line    = models.ForeignKey(
        "purchasing.ReceptionLine", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_movements"
    )
    production_record = models.ForeignKey(
        "production.ProductionRecord", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_movements"
    )
    transfer_line     = models.ForeignKey(
        "stock.InternalTransferLine", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_movements"
    )
    inventory_line    = models.ForeignKey(
        "stock.InventoryLine", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_movements"
    )

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ["-moved_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(ingredient__isnull=False, recipe__isnull=True) |
                    models.Q(ingredient__isnull=True, recipe__isnull=False)
                ),
                name="stockmovement_ingredient_xor_recipe",
            )
        ]

    def __str__(self):
        sign    = "+" if self.quantity >= 0 else ""
        article = self.ingredient or self.recipe
        return (
            f"{article} {sign}{self.quantity} {self.unit} "
            f"({self.get_movement_type_display()}) — {self.moved_at:%d/%m/%Y %H:%M}"
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._update_stock_level()

    def _update_stock_level(self):
        """Met à jour le StockLevel agrégé après chaque mouvement."""
        kwargs = {"company": self.company, "unit": self.unit, "quantity": Decimal("0")}
        if self.ingredient:
            level, _ = StockLevel.objects.get_or_create(
                company=self.company, ingredient=self.ingredient,
                defaults={**kwargs, "recipe": None}
            )
        else:
            level, _ = StockLevel.objects.get_or_create(
                company=self.company, recipe=self.recipe,
                defaults={**kwargs, "ingredient": None}
            )
        # Utilise update() pour éviter les race conditions
        if self.ingredient:
            StockLevel.objects.filter(
                company=self.company, ingredient=self.ingredient
            ).update(quantity=models.F("quantity") + self.quantity)
        else:
            StockLevel.objects.filter(
                company=self.company, recipe=self.recipe
            ).update(quantity=models.F("quantity") + self.quantity)


# ── InternalTransfer ───────────────────────────────────────────────────────────

class InternalTransfer(models.Model):
    """
    Transfert d'articles entre deux sites du même tenant.
    Ex : Boulangerie → Restaurant (pain), Boucherie → Charcuterie (viande).
    """
    STATUS_CHOICES = [
        ("draft",     "En préparation"),
        ("sent",      "Envoyé"),
        ("received",  "Réceptionné"),
        ("cancelled", "Annulé"),
    ]

    from_company = models.ForeignKey(
        Company, on_delete=models.CASCADE,
        related_name="transfers_out", verbose_name="Site expéditeur"
    )
    to_company   = models.ForeignKey(
        Company, on_delete=models.CASCADE,
        related_name="transfers_in", verbose_name="Site destinataire"
    )
    transfer_date = models.DateField(default=now, verbose_name="Date de transfert")
    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    notes         = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    sent_at       = models.DateTimeField(null=True, blank=True)
    received_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Transfert interne"
        verbose_name_plural = "Transferts internes"
        ordering = ["-transfer_date"]

    def __str__(self):
        return f"Transfert {self.from_company} → {self.to_company} ({self.transfer_date})"

    def confirm_sent(self):
        """Marque comme envoyé et crée les StockMovement transfer_out."""
        from django.utils.timezone import now as tz_now
        for line in self.lines.all():
            StockMovement.objects.create(
                company=self.from_company,
                ingredient=line.ingredient,
                recipe=line.recipe,
                movement_type="transfer_out",
                quantity=-line.quantity,
                unit=line.unit,
                transfer_line=line,
                notes=f"Transfert vers {self.to_company.name}",
            )
        self.status  = "sent"
        self.sent_at = tz_now()
        self.save(update_fields=["status", "sent_at"])

    def confirm_received(self):
        """Marque comme réceptionné et crée les StockMovement transfer_in."""
        from django.utils.timezone import now as tz_now
        for line in self.lines.all():
            # Crée un nouveau lot chez le destinataire
            batch = StockBatch.objects.create(
                company=self.to_company,
                ingredient=line.ingredient,
                recipe=line.recipe,
                quantity_initial=line.quantity,
                quantity_remaining=line.quantity,
                unit=line.unit,
                tracability_number=line.tracability_number,
                best_before=line.best_before,
                date_type=line.date_type,
            )
            StockMovement.objects.create(
                company=self.to_company,
                ingredient=line.ingredient,
                recipe=line.recipe,
                movement_type="transfer_in",
                quantity=line.quantity,
                unit=line.unit,
                stock_batch=batch,
                transfer_line=line,
                notes=f"Transfert depuis {self.from_company.name}",
            )
        self.status      = "received"
        self.received_at = tz_now()
        self.save(update_fields=["status", "received_at"])


class InternalTransferLine(models.Model):
    """Ligne d'un transfert interne."""
    transfer   = models.ForeignKey(InternalTransfer, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE,
        null=True, blank=True
    )
    recipe     = models.ForeignKey(
        Recipe, on_delete=models.CASCADE,
        null=True, blank=True
    )
    quantity           = models.DecimalField(max_digits=10, decimal_places=3)
    unit               = models.CharField(max_length=10)
    tracability_number = models.CharField(max_length=60, blank=True)
    best_before        = models.DateField(null=True, blank=True)
    date_type          = models.CharField(max_length=4, default="dluo")
    notes              = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Ligne de transfert"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(ingredient__isnull=False, recipe__isnull=True) |
                    models.Q(ingredient__isnull=True, recipe__isnull=False)
                ),
                name="transferline_ingredient_xor_recipe",
            )
        ]

    def __str__(self):
        article = self.ingredient or self.recipe
        return f"{article} × {self.quantity} {self.unit}"


# ── Inventory ──────────────────────────────────────────────────────────────────

class Inventory(models.Model):
    """
    Session d'inventaire — interface mobile/tablette (on est dans la réserve).
    """
    STATUS_CHOICES = [
        ("draft",     "En cours"),
        ("validated", "Validé"),
    ]

    company      = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="inventories")
    started_at   = models.DateTimeField(default=now)
    validated_at = models.DateTimeField(null=True, blank=True)
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    notes        = models.TextField(blank=True)

    class Meta:
        verbose_name = "Inventaire"
        verbose_name_plural = "Inventaires"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Inventaire {self.company.name} — {self.started_at:%d/%m/%Y} ({self.get_status_display()})"

    def validate(self):
        """
        Valide l'inventaire :
        - Crée un StockMovement 'inventory' pour chaque écart non nul
        - Passe le statut à 'validated'
        """
        from django.utils.timezone import now as tz_now
        for line in self.lines.all():
            delta = line.counted_quantity - line.theoretical_quantity
            if delta != 0:
                StockMovement.objects.create(
                    company=self.company,
                    ingredient=line.ingredient,
                    recipe=line.recipe,
                    movement_type="inventory",
                    quantity=delta,
                    unit=line.unit,
                    inventory_line=line,
                    notes=f"Correction inventaire du {self.started_at:%d/%m/%Y}",
                )
        self.status      = "validated"
        self.validated_at = tz_now()
        self.save(update_fields=["status", "validated_at"])


class InventoryLine(models.Model):
    """Ligne d'inventaire — un article compté."""
    inventory    = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name="lines")
    ingredient   = models.ForeignKey(Ingredient, on_delete=models.PROTECT, null=True, blank=True)
    recipe       = models.ForeignKey(Recipe, on_delete=models.PROTECT, null=True, blank=True)
    unit                 = models.CharField(max_length=10)
    theoretical_quantity = models.DecimalField(max_digits=10, decimal_places=3)
    counted_quantity     = models.DecimalField(max_digits=10, decimal_places=3)
    notes                = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Ligne d'inventaire"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(ingredient__isnull=False, recipe__isnull=True) |
                    models.Q(ingredient__isnull=True, recipe__isnull=False)
                ),
                name="inventoryline_ingredient_xor_recipe",
            ),
            models.UniqueConstraint(
                fields=["inventory", "ingredient"],
                condition=models.Q(ingredient__isnull=False),
                name="unique_ingredient_per_inventory",
            ),
            models.UniqueConstraint(
                fields=["inventory", "recipe"],
                condition=models.Q(recipe__isnull=False),
                name="unique_recipe_per_inventory",
            ),
        ]

    def __str__(self):
        article = self.ingredient or self.recipe
        return f"{article} — théorique: {self.theoretical_quantity} / compté: {self.counted_quantity}"

    @property
    def delta(self):
        return round(self.counted_quantity - self.theoretical_quantity, 3)

    @property
    def is_compliant(self):
        return self.delta == 0