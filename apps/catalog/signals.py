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

    # ── Poids total calculé si non renseigné manuellement ────────────────
    output_weight_kg = float(recipe.output_weight_kg) if recipe.output_weight_kg else None

    if not output_weight_kg:
        # Calcule depuis les lignes
        computed_weight = Decimal("0")
        for line in recipe.lines.select_related("ingredient", "sub_recipe").order_by("order"):
            if line.ingredient:
                ing = line.ingredient
                from apps.catalog.services.unit_converter import convert_to_use_unit, get_density
                qty_in_use = convert_to_use_unit(line.quantity, line.unit, ing)
                if qty_in_use is None:
                    qty_in_use = line.quantity
                if ing.use_unit == "kg":
                    computed_weight += Decimal(str(qty_in_use))
                elif ing.use_unit == "g":
                    computed_weight += Decimal(str(qty_in_use)) / 1000
                elif ing.use_unit == "litre":
                    density = get_density(ing)
                    computed_weight += Decimal(str(qty_in_use)) * density

            elif line.sub_recipe:
                sr = line.sub_recipe
                if sr.output_weight_kg:
                    # Poids proportionnel à la quantité utilisée
                    from apps.catalog.services.unit_converter import convert_units
                    qty = convert_units(
                        line.quantity, line.unit, sr.output_unit
                    )
                    if qty is None:
                        qty = line.quantity
                    ratio = Decimal(str(qty)) / Decimal(str(sr.output_quantity))
                    computed_weight += ratio * Decimal(str(sr.output_weight_kg))

        if computed_weight > 0:
            yield_rate_val = float(recipe.yield_rate) if recipe.yield_rate else 1.0
            output_weight_kg = float(computed_weight) * yield_rate_val

    # ── Valeurs nutritionnelles ───────────────────────────────────────────
    NUTRI_FIELDS = [
        "energy_kj", "energy_kcal", "fat", "saturates",
        "carbohydrates", "sugars", "protein", "salt", "fiber",
    ]

    nutrition_data = {
        "complete": False,
        "warning": "Données insuffisantes pour calculer les valeurs nutritionnelles.",
    }

    from apps.catalog.services.unit_converter import convert_to_use_unit, convert_units, get_density

    def _collect_ingredient_weights(recipe, ratio=Decimal("1"), visited=None):
        """
        Descend récursivement dans les lignes d'une recette.
        Retourne une liste de (ingredient, poids_kg) avec le ratio appliqué.
        ratio = fraction de la recette utilisée (1 = recette complète)
        """
        if visited is None:
            visited = set()
        if recipe.pk in visited:
            return []
        visited.add(recipe.pk)

        result = []
        for line in recipe.lines.select_related("ingredient", "sub_recipe").order_by("order"):
            if line.ingredient:
                ing = line.ingredient
                qty_in_use = convert_to_use_unit(line.quantity, line.unit, ing)
                if qty_in_use is None:
                    qty_in_use = line.quantity
                print(f"  {ing.name} | use_unit={ing.use_unit} | qty_in_use={qty_in_use}")
                if ing.use_unit == "kg":
                    weight_kg = Decimal(str(qty_in_use))
                elif ing.use_unit == "g":
                    weight_kg = Decimal(str(qty_in_use)) / 1000
                elif ing.use_unit == "litre":
                    density = get_density(ing)
                    weight_kg = Decimal(str(qty_in_use)) * density
                else:
                    if ing.net_weight_kg and ing.pieces_per_package:
                        weight_per_piece = (
                                Decimal(str(ing.net_weight_kg)) /
                                Decimal(str(ing.pieces_per_package))
                        )
                        weight_kg = Decimal(str(qty_in_use)) * weight_per_piece
                    else:
                        weight_kg = Decimal("0")

                result.append((ing, weight_kg * ratio))
                print(f"  -> weight_kg={weight_kg}")

            elif line.sub_recipe:
                sr = line.sub_recipe
                if sr.output_quantity and float(sr.output_quantity) > 0:
                    # Calcule le ratio de la sous-recette utilisée
                    qty_converted = convert_units(line.quantity, line.unit, sr.output_unit)
                    if qty_converted is None:
                        qty_converted = line.quantity
                    sr_ratio = Decimal(str(qty_converted)) / Decimal(str(sr.output_quantity))
                    # Applique le rendement de la sous-recette
                    sr_yield = Decimal(str(sr.yield_rate)) if sr.yield_rate else Decimal("1")
                    sr_ratio = sr_ratio / sr_yield
                    result.extend(
                        _collect_ingredient_weights(sr, ratio * sr_ratio, visited)
                    )

        return result

    ingredient_weights = _collect_ingredient_weights(recipe)
    total_weight = sum(w for _, w in ingredient_weights)
    print(f"total_weight={total_weight}, nb_ingredients={len(ingredient_weights)}")
    print(f"type total_weight={type(total_weight)}, bool={bool(total_weight > 0)}")

    missing_nutri = []
    for ing, _ in ingredient_weights:
        missing = [f for f in NUTRI_FIELDS if getattr(ing, f) is None]
        print(f"  {ing.name} missing={missing}")
        if missing:
            if ing.name not in missing_nutri:
                missing_nutri.append(ing.name)
    print(f"missing_nutri={missing_nutri}")

    if total_weight > 0:
        missing_nutri = []
        for ing, _ in ingredient_weights:
            missing = [f for f in NUTRI_FIELDS if getattr(ing, f) is None]
            if missing:
                if ing.name not in missing_nutri:
                    missing_nutri.append(ing.name)

        print(f"AVANT MISSING CHECK: total_weight={total_weight}, missing_nutri={missing_nutri}")
        if missing_nutri:
            nutrition_data = {
                "complete": False,
                "missing": missing_nutri,
                "warning": f"Valeurs nutritionnelles incomplètes pour : {', '.join(missing_nutri)}",
            }
        else:
            print("CALCUL NUTRI EN COURS")
            nutri_per_100g = {}
            for field in NUTRI_FIELDS:
                total = Decimal("0")
                for ing, weight_kg in ingredient_weights:
                    val = getattr(ing, field) or Decimal("0")
                    contribution = (weight_kg / total_weight) * Decimal(str(val))
                    total += contribution
                nutri_per_100g[field] = round(float(total), 2)

            print(f"nutri_per_100g={nutri_per_100g}")
            nutrition_data = {
                "complete": True,
                "per_100g": nutri_per_100g,
                "total_weight_kg": round(float(total_weight), 4),
            }
            print(f"nutrition_data={nutrition_data}")
    else:
        nutrition_data = {
            "complete": False,
            "warning": "Impossible de calculer le poids total — vérifiez les unités et poids des ingrédients.",
        }


    # ── Une seule requête UPDATE ──────────────────────────────────────────
    composition_data["nutrition"] = nutrition_data

    Recipe.objects.filter(pk=recipe.pk).update(
        cost_total_cached=round(Decimal(str(cost)), 4),
        is_vegan_computed=is_vegan,
        is_veggie_computed=is_veggie,
        bio_percent=bio_pct,
        composition_data=composition_data,
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