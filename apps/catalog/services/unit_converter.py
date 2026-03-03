"""
Conversion d'unités pour les lignes de recette.

Stratégie :
  1. Conversions directes (kg↔g, litre↔ml↔cl) — mathématiques pures
  2. Conversions volumétriques→masse (cs, cc, pincée) — via densité
  3. Densité : ingredient.density_kg_per_l > table INGREDIENT_DENSITIES > défaut 0.75
  4. Pièce → pas de conversion automatique (dépend de l'ingrédient)
"""
from decimal import Decimal

# ── Conversions directes vers unité de base (kg ou litre) ────────────────────
# Toutes les valeurs sont des multiplicateurs vers kg ou litre

TO_KG = {
    "kg":  Decimal("1"),
    "g":   Decimal("0.001"),
}

TO_LITRE = {
    "litre": Decimal("1"),
    "cl":    Decimal("0.01"),
    "ml":    Decimal("0.001"),
}

# Volumes en ml pour les unités "culinaires"
CULINARY_VOLUMES_ML = {
    "cs":      Decimal("15"),    # cuillère à soupe
    "cc":      Decimal("5"),     # cuillère à café
    "pincée":  Decimal("1.25"),  # ~1.5g eau, on passe par volume
}

# ── Densités par défaut (g/ml = kg/litre) ────────────────────────────────────
# Clés : mots-clés présents dans ingredient.name.lower()
INGREDIENT_DENSITIES = {
    # Liquides
    "eau":              Decimal("1.000"),
    "lait":             Decimal("1.030"),
    "crème":            Decimal("1.000"),
    "huile":            Decimal("0.920"),
    "beurre fondu":     Decimal("0.910"),
    "jus":              Decimal("1.040"),
    "vinaigre":         Decimal("1.010"),
    "sirop":            Decimal("1.300"),
    "glucose":          Decimal("1.400"),
    "miel":             Decimal("1.400"),
    # Poudres / solides
    "farine":           Decimal("0.560"),
    "sucre glace":      Decimal("0.560"),
    "sucre semoule":    Decimal("0.850"),
    "sucre":            Decimal("0.850"),
    "sel":              Decimal("1.200"),
    "cacao":            Decimal("0.500"),
    "maïzena":          Decimal("0.600"),
    "fécule":           Decimal("0.600"),
    "levure":           Decimal("0.900"),
    "bicarbonate":      Decimal("1.000"),
    "café":             Decimal("0.500"),
    "cannelle":         Decimal("0.550"),
    "poivre":           Decimal("0.530"),
    "paprika":          Decimal("0.460"),
    "curry":            Decimal("0.470"),
    "chapelure":        Decimal("0.350"),
    "noix de coco":     Decimal("0.350"),
    "amande":           Decimal("0.600"),
    "noisette":         Decimal("0.600"),
    "beurre":           Decimal("0.911"),
    "fromage":          Decimal("1.100"),
    "parmesan":         Decimal("0.400"),
    # Défaut
    "_default":         Decimal("0.750"),
}


def get_density(ingredient) -> Decimal:
    """
    Retourne la densité en kg/litre pour un ingrédient.
    Priorité : champ density_kg_per_l > table INGREDIENT_DENSITIES > défaut 0.75
    """
    # 1. Champ manuel sur l'ingrédient
    if ingredient.density_kg_per_l:
        return Decimal(str(ingredient.density_kg_per_l))

    # 2. Table par mots-clés
    name_lower = ingredient.name.lower()
    for keyword, density in INGREDIENT_DENSITIES.items():
        if keyword == "_default":
            continue
        if keyword in name_lower:
            return density

    # 3. Défaut
    return INGREDIENT_DENSITIES["_default"]


def convert_to_use_unit(
    quantity: Decimal,
    from_unit: str,
    ingredient,
) -> Decimal | None:
    """
    Convertit `quantity` depuis `from_unit` vers `ingredient.use_unit`.

    Retourne la quantité convertie, ou None si la conversion est impossible
    (ex: pièce → kg sans poids unitaire défini).

    Exemples :
      convert_to_use_unit(250, "g", ingredient_farine)    → 0.25  (kg)
      convert_to_use_unit(2, "cs", ingredient_miel)       → 0.042 (kg)
      convert_to_use_unit(3, "pièce", ingredient_oeuf)    → 3     (pièce)
    """
    quantity = Decimal(str(quantity))
    use_unit = ingredient.use_unit  # unité cible

    # ── Même unité → pas de conversion ───────────────────────────────────────
    if from_unit == use_unit:
        return quantity

    # ── Conversions masse ↔ masse ─────────────────────────────────────────────
    if from_unit in TO_KG and use_unit in TO_KG:
        return quantity * TO_KG[from_unit] / TO_KG[use_unit]

    # ── Conversions volume ↔ volume ───────────────────────────────────────────
    if from_unit in TO_LITRE and use_unit in TO_LITRE:
        return quantity * TO_LITRE[from_unit] / TO_LITRE[use_unit]

    # ── Unités culinaires (cs, cc, pincée) → masse ou volume ─────────────────
    if from_unit in CULINARY_VOLUMES_ML:
        volume_ml = quantity * CULINARY_VOLUMES_ML[from_unit]
        density = get_density(ingredient)

        if use_unit in TO_KG:
            # ml × density(kg/l) / 1000 = kg
            kg = volume_ml * density / Decimal("1000")
            return kg / TO_KG[use_unit]

        if use_unit in TO_LITRE:
            # ml → litre
            litres = volume_ml / Decimal("1000")
            return litres / TO_LITRE[use_unit]

    # ── Pincée spéciale → masse ───────────────────────────────────────────────
    # Déjà géré dans CULINARY_VOLUMES_ML

    # ── Masse → volume (nécessite densité) ───────────────────────────────────
    if from_unit in TO_KG and use_unit in TO_LITRE:
        density = get_density(ingredient)
        if density:
            kg = quantity * TO_KG[from_unit]
            litres = kg / density
            return litres / TO_LITRE[use_unit]

    # ── Volume → masse ────────────────────────────────────────────────────────
    if from_unit in TO_LITRE and use_unit in TO_KG:
        density = get_density(ingredient)
        litres = quantity * TO_LITRE[from_unit]
        kg = litres * density
        return kg / TO_KG[use_unit]

    # ── Pièce ─────────────────────────────────────────────────────────────────
    if from_unit == "pièce" and use_unit == "pièce":
        return quantity

    if from_unit == "pièce" and use_unit in TO_KG:
        # Nécessite net_weight_kg par pièce
        if ingredient.net_weight_kg and ingredient.pieces_per_package:
            weight_per_piece = (
                Decimal(str(ingredient.net_weight_kg)) /
                Decimal(str(ingredient.pieces_per_package))
            )
            kg = quantity * weight_per_piece
            return kg / TO_KG[use_unit]

    # ── Conversion impossible ─────────────────────────────────────────────────
    return None


def convert_units(quantity: Decimal, from_unit: str, to_unit: str, density: Decimal = None) -> Decimal | None:
    """
    Conversion pure sans ingrédient.
    density en kg/litre — utilisé pour conversions masse↔volume.
    """
    quantity = Decimal(str(quantity))

    if from_unit == to_unit:
        return quantity

    if from_unit in TO_KG and to_unit in TO_KG:
        return quantity * TO_KG[from_unit] / TO_KG[to_unit]

    if from_unit in TO_LITRE and to_unit in TO_LITRE:
        return quantity * TO_LITRE[from_unit] / TO_LITRE[to_unit]

    if from_unit in CULINARY_VOLUMES_ML:
        d = density or INGREDIENT_DENSITIES["_default"]
        volume_ml = quantity * CULINARY_VOLUMES_ML[from_unit]
        if to_unit in TO_KG:
            kg = volume_ml * d / Decimal("1000")
            return kg / TO_KG[to_unit]
        if to_unit in TO_LITRE:
            return (volume_ml / Decimal("1000")) / TO_LITRE[to_unit]

    if from_unit in TO_KG and to_unit in TO_LITRE and density:
        kg = quantity * TO_KG[from_unit]
        return (kg / density) / TO_LITRE[to_unit]

    if from_unit in TO_LITRE and to_unit in TO_KG and density:
        litres = quantity * TO_LITRE[from_unit]
        return (litres * density) / TO_KG[to_unit]

    return None