"""
Service OCR pour les étiquettes d'ingrédients.
Workflow :
  1. Tesseract (100% local)
  2. Si score < seuil → Mistral Vision API en fallback
  3. Parse le texte extrait → composition, allergènes, valeurs nutri, poids
  4. Remplit uniquement les champs vides de l'ingrédient (pas de conflit CIQUAL)
"""
import re
import logging
from pathlib import Path

import pytesseract
from PIL import Image, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)

# Seuil de confiance Tesseract (0-100)
TESSERACT_CONFIDENCE_THRESHOLD = 60

# Allergènes réglementaires UE (14 allergènes majeurs)
ALLERGEN_KEYWORDS = {
    "gluten":       ["gluten", "blé", "seigle", "orge", "avoine", "épeautre", "kamut", "froment"],
    "crustacés":    ["crustacé", "crevette", "homard", "crabe", "langouste"],
    "œufs":         ["œuf", "oeuf", "ovoproduit"],
    "poissons":     ["poisson", "anchois", "cabillaud", "saumon", "thon"],
    "arachides":    ["arachide", "cacahuète", "cacahuete"],
    "soja":         ["soja", "soya"],
    "lait":         ["lait", "lactose", "lactosérum", "caséine", "beurre", "crème"],
    "fruits à coque": ["amande", "noisette", "noix", "cajou", "pistache", "pécan", "macadamia"],
    "céleri":       ["céleri", "celeri"],
    "moutarde":     ["moutarde"],
    "sésame":       ["sésame", "sesame"],
    "sulfites":     ["sulfite", "dioxyde de soufre", "so2"],
    "lupin":        ["lupin"],
    "mollusques":   ["mollusque", "escargot", "moule", "huître", "calmar"],
}

# Patterns valeurs nutritionnelles
NUTRI_PATTERNS = {
    "energy_kcal":    r"(?:énergie|energie|energy)[^\d]*(\d+(?:[.,]\d+)?)\s*kcal",
    "energy_kj":      r"(?:énergie|energie|energy)[^\d]*(\d+(?:[.,]\d+)?)\s*kj",
    "fat":            r"(?:matières grasses|lipides|fat)[^\d]*(\d+(?:[.,]\d+)?)\s*g",
    "saturates":      r"(?:acides gras saturés|saturés|saturates)[^\d]*(\d+(?:[.,]\d+)?)\s*g",
    "carbohydrates":  r"(?:glucides|carbohydrates)[^\d]*(\d+(?:[.,]\d+)?)\s*g",
    "sugars":         r"(?:dont sucres|sucres|sugars)[^\d]*(\d+(?:[.,]\d+)?)\s*g",
    "protein":        r"(?:protéines|proteines|protein)[^\d]*(\d+(?:[.,]\d+)?)\s*g",
    "salt":           r"(?:sel|salt)[^\d]*(\d+(?:[.,]\d+)?)\s*g",
    "fiber":          r"(?:fibres|fiber)[^\d]*(\d+(?:[.,]\d+)?)\s*g",
}

# Pattern poids / volume
WEIGHT_PATTERNS = {
    "net_weight_kg": r"(?:poids net|net weight|poids)\s*:?\s*(\d+(?:[.,]\d+)?)\s*kg",
    "net_weight_g":  r"(?:poids net|net weight|poids)\s*:?\s*(\d+(?:[.,]\d+)?)\s*g",
    "net_volume_l":  r"(?:volume net|contenance|net volume)\s*:?\s*(\d+(?:[.,]\d+)?)\s*l",
    "net_volume_ml": r"(?:volume net|contenance|net volume)\s*:?\s*(\d+(?:[.,]\d+)?)\s*ml",
}


def preprocess_image(image_path: str) -> Image.Image:
    """Améliore la qualité de l'image avant OCR."""
    img = Image.open(image_path).convert("L")  # niveaux de gris
    # Augmente le contraste
    img = ImageEnhance.Contrast(img).enhance(2.0)
    # Légère netteté
    img = img.filter(ImageFilter.SHARPEN)
    # Redimensionne si trop petite
    w, h = img.size
    if w < 1000:
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
    return img


def ocr_with_tesseract(image_path: str) -> tuple[str, float]:
    """
    Lance Tesseract sur l'image.
    Retourne (texte, score_confiance_moyen).
    """
    img = preprocess_image(image_path)
    # Données détaillées avec score de confiance
    data = pytesseract.image_to_data(
        img,
        lang="fra+eng+deu+spa",
        output_type=pytesseract.Output.DICT,
        config="--psm 3"  # mode auto
    )
    # Calcule le score moyen (on ignore les -1)
    confidences = [int(c) for c in data["conf"] if int(c) > 0]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0

    text = pytesseract.image_to_string(img, lang="fra+eng", config="--psm 3")
    return text, avg_confidence


def ocr_with_mistral(image_path: str) -> str:
    """
    Fallback Mistral Vision si Tesseract < seuil.
    Nécessite MISTRAL_API_KEY dans les settings.
    """
    try:
        import base64
        import requests
        from django.conf import settings

        api_key = getattr(settings, "MISTRAL_API_KEY", None)
        if not api_key:
            logger.warning("MISTRAL_API_KEY non configurée — fallback Mistral impossible")
            return ""

        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        ext = Path(image_path).suffix.lower().lstrip(".")
        media_type = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"

        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "pixtral-12b-2409",
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{image_data}"}
                        },
                        {
                            "type": "text",
                            "text": (
                                "Transcris exactement le texte de cette étiquette alimentaire. "
                                "Inclus la composition, les allergènes, les valeurs nutritionnelles "
                                "et le poids net. Réponds uniquement avec le texte transcrit."
                            )
                        }
                    ]
                }],
                "max_tokens": 1000,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    except Exception as e:
        logger.error(f"Erreur Mistral Vision : {e}")
        return ""


def parse_text(text: str) -> dict:
    """
    Parse le texte OCR et extrait les données structurées.
    Retourne un dict avec les champs à remplir.
    """
    text_lower = text.lower()
    result = {}

    # ── Composition ───────────────────────────────────────────
    comp_match = re.search(
        r"(?:ingr[eé]dients?|composition)\s*:?\s*([^\n]{20,}(?:\n[^\n]+){0,5})",
        text, re.IGNORECASE
    )
    if comp_match:
        result["composition"] = comp_match.group(1).strip()

    # ── Allergènes ────────────────────────────────────────────
    found_allergens = []
    for allergen_name, keywords in ALLERGEN_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                found_allergens.append(allergen_name)
                break
    if found_allergens:
        result["allergens_found"] = found_allergens

    # ── Valeurs nutritionnelles ───────────────────────────────
    for field, pattern in NUTRI_PATTERNS.items():
        match = re.search(pattern, text_lower)
        if match:
            value = float(match.group(1).replace(",", "."))
            result[field] = value

    # ── Poids / volume ────────────────────────────────────────
    for field, pattern in WEIGHT_PATTERNS.items():
        match = re.search(pattern, text_lower)
        if match:
            value = float(match.group(1).replace(",", "."))
            if field == "net_weight_g":
                result["net_weight_kg"] = round(value / 1000, 4)
            elif field == "net_volume_ml":
                result["net_volume_l"] = round(value / 1000, 4)
            else:
                result[field] = value

    return result


def apply_ocr_results(ingredient, parsed: dict) -> list[str]:
    """
    Applique les résultats OCR sur l'ingrédient.
    Règle : ne remplit que les champs VIDES (pas de conflit CIQUAL/manuel).
    Retourne la liste des champs remplis.
    """
    from apps.utilities.models import Allergen

    filled = []

    # Champs texte / numériques
    simple_fields = [
        "composition", "net_weight_kg", "net_volume_l",
        "energy_kcal", "energy_kj", "fat", "saturates",
        "carbohydrates", "sugars", "protein", "salt", "fiber",
    ]
    for field in simple_fields:
        if field in parsed:
            current = getattr(ingredient, field, None)
            # Ne remplace que si vide
            if not current or current == 0:
                setattr(ingredient, field, parsed[field])
                filled.append(field)

    ingredient.save(update_fields=filled) if filled else None

    # Allergènes — ajoute sans supprimer les existants
    if "allergens_found" in parsed:
        for allergen_name in parsed["allergens_found"]:
            import unicodedata

            def strip_accents(s):
                return ''.join(
                    c for c in unicodedata.normalize('NFD', s)
                    if unicodedata.category(c) != 'Mn'
                ).lower()

            allergen = None
            for a in Allergen.objects.all():
                if strip_accents(a.name) == strip_accents(allergen_name) or \
                        strip_accents(allergen_name) in strip_accents(a.name):
                    allergen = a
                    break
            if allergen and allergen not in ingredient.allergens.all():
                ingredient.allergens.add(allergen)
                filled.append(f"allergène:{allergen_name}")

    return filled


def run_label_ocr(ingredient) -> dict:
    """
    Point d'entrée principal — appelé après upload de la photo.
    Retourne un rapport : {'fields_filled': [...], 'engine': 'tesseract'|'mistral', 'confidence': float}
    """
    if not ingredient.label_photo:
        return {"error": "Pas de photo"}

    image_path = ingredient.label_photo.path

    # 1. Tesseract
    text, confidence = ocr_with_tesseract(image_path)
    engine = "tesseract"

    # 2. Fallback Mistral si confiance insuffisante
    if confidence < TESSERACT_CONFIDENCE_THRESHOLD:
        logger.info(
            f"Tesseract confiance {confidence:.0f}% < {TESSERACT_CONFIDENCE_THRESHOLD}% "
            f"→ fallback Mistral pour {ingredient.name}"
        )
        mistral_text = ocr_with_mistral(image_path)
        if mistral_text:
            text = mistral_text
            engine = "mistral"
            confidence = 100  # Mistral ne retourne pas de score

    if not text.strip():
        return {"error": "Aucun texte extrait", "confidence": confidence}

    # 3. Parse + application
    parsed = parse_text(text)
    filled = apply_ocr_results(ingredient, parsed)

    logger.info(f"OCR {ingredient.name} — {engine} {confidence:.0f}% — {len(filled)} champs remplis")

    return {
        "fields_filled": filled,
        "engine": engine,
        "confidence": round(confidence, 1),
        "raw_text": text[:500],  # pour debug
    }