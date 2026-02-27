from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError

from apps.tenants.models import Tenant
from apps.utilities.models import Allergen, VatRate


# ── Catégories ─────────────────────────────────────────────────────────────────

class IngredientCategory(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="ingredient_categories")
    name = models.CharField(max_length=60, verbose_name="Nom")

    class Meta:
        verbose_name = "Catégorie d'ingrédient"
        verbose_name_plural = "Catégories d'ingrédients"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_ingredient_category_per_tenant")
        ]

    def __str__(self):
        return self.name


class RecipeCategory(models.Model):
    """Catégorie de recette (ex: Pâtisserie, Charcuterie, Sauces...)"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="recipe_categories")
    name = models.CharField(max_length=100, verbose_name="Nom")

    class Meta:
        verbose_name = "Catégorie de recette"
        verbose_name_plural = "Catégories de recettes"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_recipe_category_per_tenant")
        ]

    def __str__(self):
        return self.name


# ── Ingrédient brut ────────────────────────────────────────────────────────────

class Ingredient(models.Model):
    """
    Ingrédient brut acheté auprès d'un fournisseur.
    Ex: farine, chocolat, oeufs...
    """
    UNIT_CHOICES = [
        ("kg", "kg"),
        ("litre", "litre"),
        ("pièce", "pièce"),
        ("paquet", "paquet"),
        ("colis", "colis"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="ingredients")
    name = models.CharField(max_length=100, verbose_name="Nom")
    category = models.ForeignKey(
        IngredientCategory, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Catégorie"
    )
    allergens = models.ManyToManyField(Allergen, blank=True, verbose_name="Allergènes")
    composition = models.TextField(blank=True, verbose_name="Composition / étiquette")
    label_photo = models.ImageField(
        upload_to="ingredients/labels/",
        null=True, blank=True,
        verbose_name="Photo étiquette",
        help_text="Photo de l'étiquette pour lecture OCR"
    )

    # Unités
    purchase_unit = models.CharField(max_length=10, choices=UNIT_CHOICES, verbose_name="Unité d'achat")
    use_unit = models.CharField(max_length=10, choices=UNIT_CHOICES, verbose_name="Unité d'utilisation")

    # Poids / volume unitaire
    net_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=4, default=1,
        verbose_name="Poids net (kg/unité)",
        help_text="Poids net total de l'unité d'achat complète (kg). "
                  "Ex: colis 6×75cl d'huile → 3.6 kg. Sac farine 25kg → 25."
    )
    net_volume_l = models.DecimalField(
        max_digits=8, decimal_places=4, default=1,
        verbose_name="Volume net (l/unité)",
        help_text="Volume net total de l'unité d'achat complète (litres). "
                  "Ex: colis 6×75cl → 4.5 l. Laisser à 1 si non applicable."
    )
    density_kg_per_l = models.DecimalField(
        max_digits=5, decimal_places=3,
        null=True, blank=True,
        verbose_name="Densité (kg/l)",
        help_text="Masse d'un litre du produit. Ex: huile=0.8, eau=1.0, miel=1.4. "
                  "Laisser vide si non applicable (produits solides achetés au kg)."
    )
    pieces_per_package = models.DecimalField(
        max_digits=6, decimal_places=0, default=1,
        verbose_name="Pièces / paquet"
    )
    packages_per_purchase_unit = models.DecimalField(
        max_digits=6, decimal_places=0, default=1,
        verbose_name="Paquets / unité d'achat"
    )

    # Rendement (ex: 0.85 pour 85% après épluchage)
    yield_rate = models.DecimalField(
        max_digits=6, decimal_places=3, default=1,
        verbose_name="Rendement",
        help_text="Ex: 85 pour 85% de matière utilisable après parage"
    )

    # Prix négocié de référence (mis à jour à chaque réception)
    reference_price = models.DecimalField(
        max_digits=9, decimal_places=4, default=0,
        verbose_name="Prix de référence (HT)",
        help_text="Saisir les prix dans l'onglet Prix de la fiche ingrédient."
    )

    ciqual_ref = models.ForeignKey(
        "ciqual.CiqualIngredient",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Référence CIQUAL",
        help_text="Lien vers la base ANSES — source des valeurs nutritionnelles"
    )

    # Valeurs nutritionnelles (pour 100g)
    energy_kj = models.FloatField(null=True, blank=True, verbose_name="Énergie (kJ/100g)")
    energy_kcal = models.FloatField(null=True, blank=True, verbose_name="Énergie (kcal/100g)")
    fat = models.FloatField(null=True, blank=True, verbose_name="Lipides (g/100g)")
    saturates = models.FloatField(null=True, blank=True, verbose_name="Dont saturés (g/100g)")
    carbohydrates = models.FloatField(null=True, blank=True, verbose_name="Glucides (g/100g)")
    sugars = models.FloatField(null=True, blank=True, verbose_name="Dont sucres (g/100g)")
    protein = models.FloatField(null=True, blank=True, verbose_name="Protéines (g/100g)")
    salt = models.FloatField(null=True, blank=True, verbose_name="Sel (g/100g)")
    fiber = models.FloatField(null=True, blank=True, verbose_name="Fibres (g/100g)")

    # Flags
    is_organic = models.BooleanField(default=False, verbose_name="Bio")
    is_vegan = models.BooleanField(default=False, verbose_name="Végan")
    is_veggie = models.BooleanField(default=False, verbose_name="Végétarien")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    # Températures cibles
    target_cooking_temp = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="T° cible de cuisson (°C)",
        help_text="Ex: 70°C pour le poulet rôti"
    )
    target_keeping_temp_min = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="T° conservation minimale (°C)"
    )
    target_keeping_temp_max = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="T° conservation maximale (°C)",
        help_text="Ex: 0°C min / 2°C max pour viande hachée"
    )

    @property
    def yield_percent(self):
        """Rendement en % pour affichage (0.85 → 85)"""
        return round(float(self.yield_rate) * 100, 1)

    class Meta:
        verbose_name = "Ingrédient"
        verbose_name_plural = "Ingrédients"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_ingredient_per_tenant")
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def cost_per_use_unit(self) -> Decimal:
        """
        Coût réel par unité d'utilisation, après rendement.

        Conventions :
            - net_weight_kg  : poids net TOTAL de l'unité d'achat (kg)
            - net_volume_l   : volume net TOTAL de l'unité d'achat (litres)
            - density_kg_per_l : densité du produit (kg/l) — conversion kg ↔ litre
            - yield_rate     : rendement (0-1), ex: 0.85 pour 85% utilisable
            - purchase_unit  : unité dans laquelle on achète
            - use_unit       : unité dans laquelle on utilise en recette

        Matrice purchase_unit → use_unit :
            kg/litre → kg/litre  : prix / (poids_ou_volume × rendement)
            kg       → litre     : prix / (poids × rendement / densité)
            litre    → kg        : prix / (volume × rendement × densité)
            pièce    → pièce     : prix / (paquets × pièces)
            pièce    → kg        : prix / (net_weight_kg × rendement)
            pièce    → litre     : prix / (net_volume_l × rendement)
            paquet   → pièce     : prix / pièces_par_paquet
            paquet   → kg        : prix / (net_weight_kg × rendement)
            paquet   → litre     : prix / (net_volume_l × rendement)
            colis    → pièce     : prix / (paquets_par_colis × pièces_par_paquet)
            colis    → kg        : prix / (net_weight_kg × rendement)
            colis    → litre     : prix / (net_volume_l × rendement)
        """
        try:
            price = float(self.current_purchase_price)
            if price == 0:
                return Decimal("0")

            w = float(self.net_weight_kg)  # poids total unité achat
            v = float(self.net_volume_l)  # volume total unité achat
            y = float(self.yield_rate)  # rendement 0-1
            ppp = float(self.pieces_per_package)  # pièces par paquet
            ppu = float(self.packages_per_purchase_unit)  # paquets par unité achat
            d = float(self.density_kg_per_l) if self.density_kg_per_l else None

            pu = self.purchase_unit  # unité d'achat
            uu = self.use_unit  # unité d'utilisation

            # ── Achat au kg ───────────────────────────────────────────────────────
            if pu == "kg":
                if uu == "kg":
                    # ex: farine 25kg → utilisée au kg
                    # coût/kg = prix / (poids × rendement)
                    return Decimal(str(round(price / (w * y), 4)))
                elif uu == "litre":
                    # ex: sucre au kg utilisé au litre (peu courant)
                    # coût/l = prix / (poids × rendement / densité)
                    if not d:
                        raise ValueError(f"{self.name} : densité requise pour conversion kg→litre")
                    return Decimal(str(round(price / (w * y / d), 4)))
                elif uu == "g":
                    return Decimal(str(round(price / (w * y * 1000), 4)))

            # ── Achat au litre ────────────────────────────────────────────────────
            elif pu == "litre":
                if uu == "litre":
                    # ex: lait en bidon 10l → utilisé au litre
                    return Decimal(str(round(price / (v * y), 4)))
                elif uu == "kg":
                    # ex: huile achetée au litre utilisée au kg
                    if not d:
                        raise ValueError(f"{self.name} : densité requise pour conversion litre→kg")
                    return Decimal(str(round(price / (v * y * d), 4)))
                elif uu == "ml":
                    return Decimal(str(round(price / (v * y * 1000), 4)))

            # ── Achat à la pièce ──────────────────────────────────────────────────
            elif pu == "pièce":
                total_pieces = ppu * ppp  # paquets × pièces/paquet
                if uu == "pièce":
                    # ex: œufs achetés à la pièce utilisés à la pièce
                    return Decimal(str(round(price / (total_pieces * y), 4)))
                elif uu == "kg":
                    # ex: bouteille d'huile utilisée au kg
                    return Decimal(str(round(price / (w * y), 4)))
                elif uu == "litre":
                    # ex: bouteille d'huile 75cl utilisée au litre
                    return Decimal(str(round(price / (v * y), 4)))

            # ── Achat au paquet ───────────────────────────────────────────────────
            elif pu == "paquet":
                if uu == "pièce":
                    # ex: paquet de 6 yaourts utilisés à la pièce
                    return Decimal(str(round(price / (ppp * y), 4)))
                elif uu == "kg":
                    return Decimal(str(round(price / (w * y), 4)))
                elif uu == "litre":
                    return Decimal(str(round(price / (v * y), 4)))

            # ── Achat au colis ────────────────────────────────────────────────────
            elif pu == "colis":
                if uu == "pièce":
                    # ex: colis 6 paquets × 12 pièces = 72 pièces
                    return Decimal(str(round(price / (ppu * ppp * y), 4)))
                elif uu == "kg":
                    return Decimal(str(round(price / (w * y), 4)))
                elif uu == "litre":
                    return Decimal(str(round(price / (v * y), 4)))

            # Cas non géré
            raise ValueError(f"{self.name} : combinaison {pu}→{uu} non gérée")

        except (TypeError, ZeroDivisionError, ValueError) as e:
            import logging
            logging.getLogger(__name__).warning(f"cost_per_use_unit error: {e}")
            return Decimal("0")

    @property
    def cost_per_kg(self) -> Decimal:
        """
        Alias rétrocompatible — utilisé dans RecipeLine.line_cost.
        Redirige vers cost_per_use_unit.
        """
        return self.cost_per_use_unit

    @property
    def current_purchase_price(self) -> Decimal:
        """
        Prix d'achat courant depuis PriceRecord.
        Fallback sur reference_price pendant la transition.
        """
        from apps.pricing.models import PriceRecord
        from django.utils import timezone
        today = timezone.localdate()
        record = (
            PriceRecord.objects
            .filter(
                ingredient=self,
                channel="purchase",
                valid_from__lte=today,
            )
            .filter(
                models.Q(valid_until__isnull=True) |
                models.Q(valid_until__gte=today)
            )
            .order_by("-valid_from")
            .first()
        )
        if record:
            return record.price_ht
        return self.reference_price  # fallback temporaire

    @property
    def allergen_list(self):
        return ", ".join(self.allergens.values_list("name", flat=True))


# ══════════════════════════════════════════════════════════════════════════════
# RECETTES & SOUS-RECETTES
# ══════════════════════════════════════════════════════════════════════════════

class Recipe(models.Model):
    """
    Recette ou sous-recette.

    Un même objet Recipe peut jouer plusieurs rôles simultanément :
      - Sous-recette (ingrédient d'une autre recette)  → used as RecipeLine.sub_recipe
      - Produit fini vendable                          → is_sellable = True
      - Les deux à la fois (ex: ketchup maison)        → is_sellable = True + used as sub_recipe

    Niveaux :
      RECIPE     = recette simple (ingrédients bruts uniquement)
      SUB_RECIPE = contient au moins une sous-recette
      PRODUCT    = produit fini (peut contenir sous-recettes)

    Note : ces types sont indicatifs. Le modèle supporte N niveaux d'imbrication
    sans limite technique. La seule contrainte est l'absence de cycle
    (A→B→A interdit, détecté dans clean()).
    """

    RECIPE_TYPE_CHOICES = [
        ("recipe", "Recette simple"),
        ("sub_recipe", "Sous-recette / semi-fini"),
        ("product", "Produit fini"),
    ]

    UNIT_CHOICES = [
        ("kg", "kg"),
        ("litre", "litre"),
        ("pièce", "pièce"),
        ("portion", "portion"),
        ("cadre", "cadre"),
        ("plaque", "plaque"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="recipes")
    name = models.CharField(max_length=200, verbose_name="Nom")
    category = models.ForeignKey(
        RecipeCategory, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Catégorie"
    )
    recipe_type = models.CharField(
        max_length=20, choices=RECIPE_TYPE_CHOICES,
        default="recipe", verbose_name="Type"
    )

    # ── Production ────────────────────────────────────────────────────────────
    output_quantity = models.DecimalField(
        max_digits=10, decimal_places=4, default=1,
        verbose_name="Quantité produite",
        help_text="Ex: 1 cadre 60x40, 12 portions, 2.5 kg"
    )
    output_unit = models.CharField(
        max_length=10, choices=UNIT_CHOICES,
        default="pièce", verbose_name="Unité de production"
    )
    output_weight_kg = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
        verbose_name="Poids total produit (kg)",
        help_text="Poids réel après cuisson/assemblage — sert au calcul nutritionnel"
    )
    shelf_life_days = models.PositiveSmallIntegerField(default=0, verbose_name="DLC (jours)")
    shelf_life_after_opening_days = models.PositiveSmallIntegerField(
        default=0, verbose_name="DLC après ouverture (jours)"
    )

    # ── Vente ─────────────────────────────────────────────────────────────────
    is_sellable = models.BooleanField(
        default=False, verbose_name="Vendable tel quel",
        help_text="Cochez si cette recette peut être vendue directement (ex: ketchup maison, mousse au chocolat)"
    )
    selling_price_ht = models.DecimalField(
        max_digits=9, decimal_places=4, null=True, blank=True,
        verbose_name="Prix de vente HT",
        help_text="Rempli uniquement si vendable tel quel"
    )
    selling_price_ttc = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name="Prix de vente TTC"
    )
    vat_rate = models.ForeignKey(
        VatRate, on_delete=models.PROTECT,
        null=True, blank=True, verbose_name="Taux de TVA"
    )


    # ── Infos ─────────────────────────────────────────────────────────────────
    notes = models.TextField(blank=True, verbose_name="Notes / conseils")
    photo = models.ImageField(
        upload_to="recipes/photos/",
        null=True, blank=True, verbose_name="Photo"
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Recette"
        verbose_name_plural = "Recettes"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_recipe_per_tenant")
        ]

    def __str__(self):
        return self.name

    # ── Détection de cycle ────────────────────────────────────────────────────
    def _get_all_sub_recipe_ids(self, visited=None) -> set:
        """
        Parcours en profondeur (DFS) de toutes les sous-recettes utilisées.
        Retourne l'ensemble des IDs de recettes accessibles depuis self.
        Utilisé pour détecter les cycles avant sauvegarde.

        Exemple de cycle interdit :
          Mousse (id=1) → Crème (id=2) → Mousse (id=1)  ← cycle !
        """
        if visited is None:
            visited = set()
        for line in self.lines.filter(sub_recipe__isnull=False).select_related("sub_recipe"):
            sr_id = line.sub_recipe_id
            if sr_id not in visited:
                visited.add(sr_id)
                line.sub_recipe._get_all_sub_recipe_ids(visited)
        return visited

    def clean(self):
        """
        Valide l'absence de cycle avant sauvegarde.
        Appelé automatiquement par Django lors de full_clean() et dans les formulaires.
        """
        from django.core.exceptions import ValidationError
        if self.pk:
            sub_ids = self._get_all_sub_recipe_ids()
            if self.pk in sub_ids:
                raise ValidationError(
                    f"Cycle détecté : '{self.name}' est déjà utilisée comme "
                    f"sous-recette dans sa propre chaîne de recettes."
                )

    # ── Calcul prix de revient ─────────────────────────────────────────────────
    @property
    def cost_total(self) -> float:
        """
        Coût total de production de la recette (toutes lignes confondues).
        Récursif : descend dans les sous-recettes pour obtenir leur coût unitaire.

        Formule par ligne :
          - Ingrédient : qty × (prix_ref / poids_net_kg) / rendement
          - Sous-recette : qty × sous_recette.cost_per_unit
        """
        total = 0.0
        for line in self.lines.select_related("ingredient", "sub_recipe"):
            total += line.line_cost
        return round(total, 4)

    @property
    def cost_per_unit(self) -> float:
        """
        Coût par unité produite.
        Ex: recette produit 12 portions → cost_per_unit = cost_total / 12
        """
        qty = float(self.output_quantity) or 1
        return round(self.cost_total / qty, 4)

    @property
    def current_selling_price(self) -> dict | None:
        """
        Prix de vente courant depuis PriceRecord.
        Retourne {'ht': Decimal, 'ttc': Decimal, 'vat': VatRate, 'channel': str}
        ou None si aucun prix de vente défini.
        Priorité retail > wholesale si les deux existent à la même date.
        """
        from apps.pricing.models import PriceRecord
        from django.utils import timezone
        today = timezone.localdate()
        record = (
            PriceRecord.objects
            .filter(
                recipe=self,
                channel__in=("retail", "wholesale"),
                valid_from__lte=today,
            )
            .filter(
                models.Q(valid_until__isnull=True) |
                models.Q(valid_until__gte=today)
            )
            .select_related("vat_rate")
            .order_by(
                models.Case(
                    models.When(channel="retail", then=0),
                    models.When(channel="wholesale", then=1),
                    default=2,
                ),
                "-valid_from"
            )
            .first()
        )
        if not record:
            return None
        return {
            "ht": record.price_ht,
            "ttc": record.price_ttc,
            "vat": record.vat_rate,
            "channel": record.get_channel_display(),
        }

    @property
    def margin(self) -> float | None:
        """
        Marge brute en € = prix de vente HT courant - coût de revient par unité.
        None si aucun prix de vente défini.
        """
        sp = self.current_selling_price
        if sp and sp["ht"] and self.cost_per_unit:
            return round(float(sp["ht"]) - self.cost_per_unit, 4)
        return None

    @property
    def margin_rate(self) -> float | None:
        """
        Taux de marge en % = (marge / prix HT) × 100.
        None si aucun prix de vente défini.
        """
        sp = self.current_selling_price
        if self.margin is not None and sp and sp["ht"]:
            return round(self.margin / float(sp["ht"]) * 100, 1)
        return None


class RecipeLine(models.Model):
    """
    Ligne d'une recette — représente UN ingrédient OU UNE sous-recette.

    Règle métier fondamentale :
      - ingredient XOR sub_recipe : exactement l'un des deux doit être rempli.
      - Cette contrainte est enforced à deux niveaux :
          1. CheckConstraint en base de données (garantie absolue)
          2. Validation dans clean() pour un message d'erreur lisible

    Exemples :
      Mousse au chocolat :
        line 1 : ingredient=Chocolat noir,  quantity=200, unit=g
        line 2 : ingredient=Œufs,           quantity=4,   unit=pièce
        line 3 : ingredient=Sucre,          quantity=80,  unit=g

      Entremet chocolat :
        line 1 : sub_recipe=Mousse chocolat, quantity=1,   unit=portion
        line 2 : ingredient=Biscuit Joconde, quantity=300, unit=g
        line 3 : sub_recipe=Copeaux choco,  quantity=50,  unit=g
    """

    UNIT_CHOICES = [
        ("kg", "kg"),
        ("g", "g"),
        ("litre", "litre"),
        ("ml", "ml"),
        ("pièce", "pièce"),
        ("portion", "portion"),
        ("cs", "c. à soupe"),
        ("cc", "c. à café"),
        ("pincée", "pincée"),
    ]

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="lines")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")

    # ── Source : ingrédient brut OU sous-recette (jamais les deux) ────────────
    ingredient = models.ForeignKey(
        "catalog.Ingredient",
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name="Ingrédient",
        help_text="Laisser vide si c'est une sous-recette"
    )
    sub_recipe = models.ForeignKey(
        Recipe,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="used_in_lines",
        verbose_name="Sous-recette",
        help_text="Laisser vide si c'est un ingrédient brut"
    )

    quantity = models.DecimalField(
        max_digits=10, decimal_places=4,
        verbose_name="Quantité"
    )
    unit = models.CharField(
        max_length=10, choices=UNIT_CHOICES,
        verbose_name="Unité"
    )
    notes = models.CharField(
        max_length=200, blank=True,
        verbose_name="Notes",
        help_text="Ex: tamiser avant, température ambiante, haché finement..."
    )

    class Meta:
        verbose_name = "Ligne de recette"
        verbose_name_plural = "Lignes de recette"
        ordering = ["order"]
        constraints = [
            # Garantie base de données : ingredient XOR sub_recipe
            models.CheckConstraint(
                check=(
                        models.Q(ingredient__isnull=False, sub_recipe__isnull=True) |
                        models.Q(ingredient__isnull=True, sub_recipe__isnull=False)
                ),
                name="recipeline_ingredient_xor_subrecipe",
                violation_error_message="Une ligne doit avoir soit un ingrédient, soit une sous-recette — pas les deux, pas aucun."
            )
        ]

    def __str__(self):
        source = self.ingredient or self.sub_recipe
        return f"{self.recipe.name} — {source} × {self.quantity} {self.unit}"

    def clean(self):
        """Message d'erreur lisible si la contrainte XOR est violée."""
        from django.core.exceptions import ValidationError
        if self.ingredient and self.sub_recipe:
            raise ValidationError("Une ligne ne peut pas avoir à la fois un ingrédient et une sous-recette.")
        if not self.ingredient and not self.sub_recipe:
            raise ValidationError("Une ligne doit avoir soit un ingrédient, soit une sous-recette.")

    @property
    def line_cost(self) -> float:
        """
        Coût de cette ligne en €.
        Utilise cost_per_use_unit de l'ingrédient — gère toutes les
        combinaisons purchase_unit → use_unit avec densité et rendement.
        """
        try:
            qty = float(self.quantity)
            if self.ingredient:
                return round(qty * float(self.ingredient.cost_per_use_unit), 4)
            elif self.sub_recipe:
                return round(qty * self.sub_recipe.cost_per_unit, 4)
        except (TypeError, ZeroDivisionError):
            return 0.0
        return 0.0


class RecipeStep(models.Model):
    """
    Étape de fabrication d'une recette.
    Ordonnée, avec durée, température et photo optionnelle.

    Ex pour une mousse au chocolat :
      step 1 : "Faire fondre le chocolat"  — 5 min — 50°C
      step 2 : "Monter les blancs en neige" — 10 min
      step 3 : "Incorporer délicatement"    — 3 min
      step 4 : "Réserver au frais"          — 120 min — 4°C
    """
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")
    title = models.CharField(max_length=200, verbose_name="Titre de l'étape")
    description = models.TextField(blank=True, verbose_name="Description détaillée")
    duration_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Durée (min)"
    )
    temperature_c = models.DecimalField(
        max_digits=5, decimal_places=1,
        null=True, blank=True, verbose_name="Température (°C)",
        help_text="Ex: 180 pour un four, 4 pour une cellule de refroidissement"
    )
    photo = models.ImageField(
        upload_to="recipes/steps/",
        null=True, blank=True, verbose_name="Photo de l'étape"
    )

    class Meta:
        verbose_name = "Étape de recette"
        verbose_name_plural = "Étapes de recette"
        ordering = ["order"]

    def __str__(self):
        return f"{self.recipe.name} — Étape {self.order} : {self.title}"


class RecipeStepPhoto(models.Model):
    """
    Photo illustrant une étape de fabrication (tour de main).
    Plusieurs photos possibles par étape.
    """
    step = models.ForeignKey(RecipeStep, on_delete=models.CASCADE, related_name="photos")
    photo = models.ImageField(upload_to="recipe_steps/", verbose_name="Photo")
    caption = models.CharField(max_length=200, blank=True, verbose_name="Légende")
    order = models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")

    class Meta:
        verbose_name = "Photo d'étape"
        verbose_name_plural = "Photos d'étapes"
        ordering = ["step", "order"]

    def __str__(self):
        return f"{self.step} — photo {self.order}"


class RecipeEquipment(models.Model):
    """
    Équipement utilisé dans une recette avec sa taille de lot.

    Ex: Recette brioche
      → Pétrin 20kg  | batch_size=20 | batch_unit=kg  | step=Étape 1 (pétrissage)
      → Moule 12     | batch_size=12 | batch_unit=pièce | step=Étape 3 (moulage)

    Le planning utilise batch_size pour calculer le nombre de cycles :
      besoin=50kg, batch_size=20kg → ceil(50/20) = 3 pétrins
    """

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="equipment_lines")
    equipment = models.ForeignKey(
        "company.Equipment", on_delete=models.PROTECT,
        verbose_name="Équipement"
    )
    batch_size = models.DecimalField(
        max_digits=8, decimal_places=3,
        verbose_name="Taille de lot",
        help_text="Quantité produite par cycle sur cet équipement"
    )
    batch_unit = models.CharField(max_length=10, verbose_name="Unité")
    step = models.ForeignKey(
        RecipeStep, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="equipment_lines",
        verbose_name="Étape associée"
    )
    notes = models.CharField(max_length=200, blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Équipement de recette"
        verbose_name_plural = "Équipements de recette"
        ordering = ["recipe", "step__order"]

    def __str__(self):
        return f"{self.recipe.name} — {self.equipment.name} ({self.batch_size} {self.batch_unit})"

    def cycles_needed(self, total_quantity):
        """
        Calcule le nombre de cycles nécessaires pour une quantité donnée.
        Ex: total=50kg, batch_size=20kg → 3 cycles (2 pleins + 1 partiel)
        """
        import math
        if self.batch_size and self.batch_size > 0:
            return math.ceil(total_quantity / self.batch_size)
        return 1