from django.db import models
from apps.tenants.models import Tenant


class CiqualIngredient(models.Model):
    """
    Base nutritionnelle ANSES-CIQUAL.
    Table SHARED (schema public) — immuable, partagée par tous les tenants.
    Import depuis le CSV officiel ANSES via management command :
      python manage.py import_ciqual <path/to/ciqual.csv>

    Valeurs pour 100g de produit.
    Les valeurs peuvent être None si non renseignées dans la base CIQUAL.
    Le préfixe '<' dans la base CIQUAL (ex: '< 0.5') est ignoré, on prend la valeur numérique.
    """
    ciqual_code = models.CharField(
        max_length=20, unique=True, verbose_name="Code CIQUAL"
    )
    name_fr = models.CharField(max_length=200, verbose_name="Nom français")
    name_en = models.CharField(max_length=200, blank=True, verbose_name="Nom anglais")
    group = models.CharField(max_length=100, blank=True, verbose_name="Groupe CIQUAL")
    sub_group = models.CharField(max_length=100, blank=True, verbose_name="Sous-groupe CIQUAL")

    # Énergie
    energy_kj = models.FloatField(null=True, blank=True, verbose_name="Énergie (kJ/100g)")
    energy_kcal = models.FloatField(null=True, blank=True, verbose_name="Énergie (kcal/100g)")

    # Macronutriments
    water = models.FloatField(null=True, blank=True, verbose_name="Eau (g/100g)")
    protein = models.FloatField(null=True, blank=True, verbose_name="Protéines (g/100g)")
    carbohydrates = models.FloatField(null=True, blank=True, verbose_name="Glucides (g/100g)")
    sugars = models.FloatField(null=True, blank=True, verbose_name="Dont sucres (g/100g)")
    fat = models.FloatField(null=True, blank=True, verbose_name="Lipides (g/100g)")
    saturates = models.FloatField(null=True, blank=True, verbose_name="Dont saturés (g/100g)")
    fiber = models.FloatField(null=True, blank=True, verbose_name="Fibres (g/100g)")
    salt = models.FloatField(null=True, blank=True, verbose_name="Sel (g/100g)")

    # Micronutriments (les plus courants en étiquetage)
    sodium = models.FloatField(null=True, blank=True, verbose_name="Sodium (mg/100g)")
    calcium = models.FloatField(null=True, blank=True, verbose_name="Calcium (mg/100g)")
    iron = models.FloatField(null=True, blank=True, verbose_name="Fer (mg/100g)")
    vitamin_c = models.FloatField(null=True, blank=True, verbose_name="Vitamine C (mg/100g)")
    vitamin_d = models.FloatField(null=True, blank=True, verbose_name="Vitamine D (µg/100g)")

    class Meta:
        verbose_name = "Ingrédient CIQUAL"
        verbose_name_plural = "Ingrédients CIQUAL"
        ordering = ["name_fr"]

    def __str__(self):
        return f"{self.name_fr} ({self.ciqual_code})"

    def to_nutrition_dict(self):
        """Retourne les valeurs nutritionnelles sous forme de dict — pour copie dans Ingredient."""
        return {
            "energy_kj": self.energy_kj,
            "energy_kcal": self.energy_kcal,
            "fat": self.fat,
            "saturates": self.saturates,
            "carbohydrates": self.carbohydrates,
            "sugars": self.sugars,
            "protein": self.protein,
            "salt": self.salt,
            "fiber": self.fiber,
        }


class TenantCiqualMapping(models.Model):
    """
    Apprentissage par tenant : mémorise quelle entrée CIQUAL
    a été choisie pour un nom d'ingrédient donné.

    Permet de pré-sélectionner la bonne entrée au prochain appel.
    Ex: tenant Boulangerie Martin → "huile" → "Huile d'olive extra vierge"
        plutôt que de proposer "Huile d'olive" en premier.

    Clé de recherche : ingredient_name_lower (nom normalisé en minuscules).
    Score : nombre de fois que ce mapping a été confirmé (pour tri).
    """
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="ciqual_mappings"
    )
    ingredient_name_lower = models.CharField(
        max_length=200,
        verbose_name="Nom ingrédient normalisé",
        help_text="Nom en minuscules, sans accents — clé de recherche"
    )
    ciqual_ingredient = models.ForeignKey(
        CiqualIngredient, on_delete=models.CASCADE,
        verbose_name="Entrée CIQUAL associée"
    )
    score = models.PositiveIntegerField(
        default=1,
        verbose_name="Score d'apprentissage",
        help_text="Incrémenté à chaque confirmation — utilisé pour le tri"
    )
    last_used = models.DateTimeField(auto_now=True, verbose_name="Dernière utilisation")

    class Meta:
        verbose_name = "Mapping CIQUAL (apprentissage)"
        verbose_name_plural = "Mappings CIQUAL (apprentissage)"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "ingredient_name_lower", "ciqual_ingredient"],
                name="unique_tenant_ciqual_mapping"
            )
        ]
        ordering = ["-score", "-last_used"]

    def __str__(self):
        return (
            f"{self.tenant.name} : '{self.ingredient_name_lower}' "
            f"→ {self.ciqual_ingredient.name_fr} (score: {self.score})"
        )