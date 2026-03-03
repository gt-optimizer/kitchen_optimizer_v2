"""
Signaux catalog — deux responsabilités :
  1. trigger_label_ocr    : déclenche l'OCR quand label_photo change
  2. on_ingredient_change : propage les changements d'ingrédient aux recettes
  3. on_recipe_line_change: recalcule la recette quand une ligne change
"""
import logging
from decimal import Decimal

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Ingredient, Recipe, RecipeLine

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# OCR
# ══════════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender=Ingredient)
def trigger_label_ocr(sender, instance, created, update_fields, **kwargs):
    """
    Déclenche l'OCR automatiquement quand label_photo est modifié.
    La garde update_fields évite la boucle infinie avec apply_ocr_results.
    """
    if update_fields and "label_photo" not in update_fields:
        return

    if instance.label_photo:
        from .services.label_ocr import run_label_ocr
        try:
            result = run_label_ocr(instance)
            from django.core.cache import cache
            cache.set(f"ocr_result_{instance.pk}", result, timeout=300)
        except Exception as e:
            logger.error(f"OCR signal erreur : {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Recalcul recettes
# ══════════════════════════════════════════════════════════════════════════════

def _collect_ingredients(recipe, visited_recipes=None):
    """
    Descend récursivement dans les sous-recettes.
    Retourne la liste de tous les Ingredient utilisés (avec doublons possibles).
    visited_recipes évite les boucles infinies.
    """
    if visited_recipes is None:
        visited_recipes = set()
    if recipe.pk in visited_recipes:
        return []
    visited_recipes.add(recipe.pk)

    result = []
    for line in recipe.lines.select_related(
        "ingredient", "sub_recipe"
    ).prefetch_related("ingredient__allergens"):
        if line.ingredient:
            result.append(line.ingredient)
        elif line.sub_recipe:
            result.extend(_collect_ingredients(line.sub_recipe, visited_recipes))
    return result


def _recompute_recipe(recipe):
    """
    Recalcule et met à jour tous les champs cachés d'une recette en une requête.
    """
    ingredients = _collect_ingredients(recipe)

    # ── Coût total ────────────────────────────────────────────────────────
    cost = sum(
        line.line_cost
        for line in recipe.lines.select_related("ingredient", "sub_recipe")
    )

    # ── Vegan / Veggie / Bio ──────────────────────────────────────────────
    if ingredients:
        is_vegan   = all(i.is_vegan  for i in ingredients)
        is_veggie  = all(i.is_veggie for i in ingredients)
        bio_count  = sum(1 for i in ingredients if i.is_organic)
        bio_pct    = round(Decimal(bio_count) / Decimal(len(ingredients)) * 100, 1)
    else:
        is_vegan = is_veggie = False
        bio_pct = Decimal("0")

    # ── Composition JSON (dédupliquée) ────────────────────────────────────
    seen_ids = set()
    composition_ingredients = []
    for ing in ingredients:
        if ing.pk not in seen_ids:
            seen_ids.add(ing.pk)
            composition_ingredients.append({
                "name":        ing.name,
                "allergens":   list(ing.allergens.values_list("name", flat=True)),
                "composition": ing.composition or "",
                "is_organic":  ing.is_organic,
            })

    from django.utils import timezone
    composition_data = {
        "ingredients": composition_ingredients,
        "allergens_bold": sorted({
            a
            for ing_data in composition_ingredients
            for a in ing_data["allergens"]
        }),
        "updated_at": timezone.now().isoformat(),
    }

    # ── Une seule requête UPDATE ──────────────────────────────────────────
    Recipe.objects.filter(pk=recipe.pk).update(
        cost_total_cached  = round(Decimal(str(cost)), 4),
        is_vegan_computed  = is_vegan,
        is_veggie_computed = is_veggie,
        bio_percent        = bio_pct,
        composition_data   = composition_data,
    )
    logger.debug(f"Recipe #{recipe.pk} '{recipe.name}' recalculée — coût={cost:.4f}€")


def _propagate_to_parents(recipe, visited=None):
    """
    Remonte la chaîne : recalcule toutes les recettes parentes
    qui utilisent cette recette comme sous-recette.
    visited évite les boucles infinies.
    """
    if visited is None:
        visited = set()
    if recipe.pk in visited:
        return
    visited.add(recipe.pk)

    parent_ids = (
        RecipeLine.objects
        .filter(sub_recipe=recipe)
        .values_list("recipe_id", flat=True)
        .distinct()
    )
    for parent in Recipe.objects.filter(pk__in=parent_ids):
        _recompute_recipe(parent)
        _propagate_to_parents(parent, visited)


# ── Signal : ligne de recette modifiée ────────────────────────────────────────

@receiver(post_save, sender=RecipeLine)
@receiver(post_delete, sender=RecipeLine)
def on_recipe_line_change(sender, instance, **kwargs):
    """Une ligne de recette change → recalcule la recette parente + ses parents."""
    try:
        _recompute_recipe(instance.recipe)
        _propagate_to_parents(instance.recipe)
    except Exception as e:
        logger.error(f"on_recipe_line_change erreur : {e}")


# ── Signal : ingrédient modifié ───────────────────────────────────────────────

@receiver(post_save, sender=Ingredient)
def on_ingredient_change(sender, instance, update_fields, **kwargs):
    """
    Un ingrédient change → recalcule toutes les recettes qui l'utilisent.
    Ignoré si seule label_photo change (géré par trigger_label_ocr).
    """
    # Évite le recalcul si seule la photo change
    if update_fields and set(update_fields) <= {"label_photo"}:
        return

    try:
        direct_recipe_ids = (
            RecipeLine.objects
            .filter(ingredient=instance)
            .values_list("recipe_id", flat=True)
            .distinct()
        )
        for recipe in Recipe.objects.filter(pk__in=direct_recipe_ids):
            _recompute_recipe(recipe)
            _propagate_to_parents(recipe)
    except Exception as e:
        logger.error(f"on_ingredient_change erreur : {e}")