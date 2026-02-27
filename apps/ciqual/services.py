"""
apps/ciqual/services.py

Service de recherche floue dans la base CIQUAL.
Utilisé par le bouton "Calculer valeurs nutritionnelles" sur la fiche ingrédient.

Workflow :
  1. search_ciqual(name, tenant) → liste des 5 meilleurs résultats
     - Les mappings appris par le tenant remontent en premier
     - Les autres sont triés par similarité (difflib)
  2. confirm_mapping(name, ciqual_id, tenant) → mémorise le choix
  3. apply_to_ingredient(ingredient, ciqual_ingredient) → copie les valeurs
"""
import difflib
import unicodedata

from .models import CiqualIngredient, TenantCiqualMapping


def normalize(text: str) -> str:
    """Normalise un texte pour la comparaison : minuscules, sans accents."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


def search_ciqual(ingredient_name: str, tenant, limit: int = 5) -> list[dict]:
    """
    Cherche les entrées CIQUAL les plus proches du nom d'ingrédient.

    Retourne une liste de dicts triée par pertinence :
    [
      {
        'ciqual': <CiqualIngredient>,
        'score': float,          # similarité 0-1
        'learned': bool,         # True si issu de l'apprentissage tenant
        'learn_score': int,      # score d'apprentissage (0 si pas appris)
      },
      ...
    ]

    Priorité : mappings appris par le tenant > similarité difflib
    """
    name_normalized = normalize(ingredient_name)

    # 1. Récupère les mappings appris pour ce tenant
    learned_mappings = TenantCiqualMapping.objects.filter(
        tenant=tenant,
        ingredient_name_lower=name_normalized,
    ).select_related("ciqual_ingredient").order_by("-score")

    learned_ids = []
    results = []

    for mapping in learned_mappings:
        learned_ids.append(mapping.ciqual_ingredient_id)
        results.append({
            "ciqual": mapping.ciqual_ingredient,
            "score": 1.0,  # score max pour les entrées apprises
            "learned": True,
            "learn_score": mapping.score,
        })

    if len(results) >= limit:
        return results[:limit]

    # 2. Recherche floue sur les noms CIQUAL restants
    all_ciqual = CiqualIngredient.objects.exclude(pk__in=learned_ids)
    names = list(all_ciqual.values_list("name_fr", "pk"))

    name_list = [normalize(n[0]) for n in names]
    close_matches = difflib.get_close_matches(
        name_normalized, name_list,
        n=limit - len(results) + 5,  # on prend un peu plus pour avoir le choix
        cutoff=0.3
    )

    seen_pks = set(learned_ids)
    for match in close_matches:
        if len(results) >= limit:
            break
        # Retrouve le pk correspondant
        for name_fr, pk in names:
            if normalize(name_fr) == match and pk not in seen_pks:
                try:
                    ciqual = all_ciqual.get(pk=pk)
                    similarity = difflib.SequenceMatcher(
                        None, name_normalized, match
                    ).ratio()
                    results.append({
                        "ciqual": ciqual,
                        "score": round(similarity, 3),
                        "learned": False,
                        "learn_score": 0,
                    })
                    seen_pks.add(pk)
                except CiqualIngredient.DoesNotExist:
                    pass
                break

    return results[:limit]


def confirm_mapping(ingredient_name: str, ciqual_ingredient: CiqualIngredient, tenant) -> None:
    """
    Mémorise ou incrémente le score d'un mapping tenant ↔ CIQUAL.
    Appelé quand l'utilisateur clique sur une entrée CIQUAL.
    """
    name_normalized = normalize(ingredient_name)

    mapping, created = TenantCiqualMapping.objects.get_or_create(
        tenant=tenant,
        ingredient_name_lower=name_normalized,
        ciqual_ingredient=ciqual_ingredient,
        defaults={"score": 1},
    )
    if not created:
        mapping.score += 1
        mapping.save(update_fields=["score", "last_used"])


def apply_to_ingredient(ingredient, ciqual_ingredient: CiqualIngredient) -> None:
    """
    Copie les valeurs nutritionnelles CIQUAL dans un Ingredient.
    Met aussi à jour la FK ciqual_ref.
    """
    nutrition = ciqual_ingredient.to_nutrition_dict()
    for field, value in nutrition.items():
        setattr(ingredient, field, value)

    ingredient.ciqual_ref = ciqual_ingredient
    ingredient.save(update_fields=list(nutrition.keys()) + ["ciqual_ref"])