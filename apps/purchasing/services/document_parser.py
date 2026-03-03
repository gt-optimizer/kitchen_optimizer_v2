"""
Service de parsing des documents de livraison (BL/factures).

Pipeline :
  1. PyMuPDF  → extraction texte natif (rapide, gratuit)
  2. Mistral Vision → fallback si page image ou confiance < seuil
  3. Parsing lignes → détection produits / taxes filière / remises / frais port
  4. Matching fuzzy → association ingrédients BDD
"""
import re
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

import fitz  # PyMuPDF
from rapidfuzz import fuzz, process

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Dictionnaire taxes filière viande ────────────────────────────────────────
SECTOR_TAX_PATTERNS = [
    r'\bCVO\b',
    r'\bINAPORC\b',
    r'\bINTERBEV\b',
    r'\bIP3V?\b',
    r'\bIP5\b',
    r'\bRSD\b',
    r'\bTEO\b',
]
SECTOR_TAX_RE = re.compile('|'.join(SECTOR_TAX_PATTERNS), re.IGNORECASE)

# ── Patterns remises ──────────────────────────────────────────────────────────
DISCOUNT_PATTERNS = [
    r'remise',
    r'rabais',
    r'avoir',
    r'ristourne',
    r'franco',
    r'réduction',
    r'reduction',
]
DISCOUNT_RE = re.compile('|'.join(DISCOUNT_PATTERNS), re.IGNORECASE)

# ── Patterns frais de port ────────────────────────────────────────────────────
SHIPPING_PATTERNS = [
    r'port',
    r'livraison',
    r'transport',
    r'frais\s+de\s+port',
    r'franco\s+de\s+port',
]
SHIPPING_RE = re.compile('|'.join(SHIPPING_PATTERNS), re.IGNORECASE)

# ── Pattern prix ──────────────────────────────────────────────────────────────
PRICE_RE = re.compile(r'(\d{1,6}[.,]\d{2,4})')
QTY_RE   = re.compile(r'(\d{1,6}[.,]\d{0,3})\s*(kg|g|l|litre|pièce|pce|pc|boite|bt|colis|col|sac)', re.IGNORECASE)


def extract_text_from_pdf(filepath: str) -> list[dict]:
    """
    Extrait le texte de chaque page d'un PDF via PyMuPDF.
    Retourne une liste de dicts {page: int, text: str, has_text: bool}
    """
    pages = []
    try:
        doc = fitz.open(filepath)
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            pages.append({
                "page":     i + 1,
                "text":     text,
                "has_text": len(text) > 50,  # < 50 chars = probablement une image
            })
        doc.close()
    except Exception as e:
        logger.error(f"PyMuPDF error on {filepath}: {e}")
    return pages


def extract_text_via_mistral(filepath: str, page_number: int) -> Optional[str]:
    """
    Fallback OCR via Mistral Vision pour les pages sans texte natif.
    """
    try:
        import base64
        import httpx

        # Convertit la page en image
        doc = fitz.open(filepath)
        page = doc[page_number - 1]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()

        img_b64 = base64.b64encode(img_bytes).decode()

        api_key = settings.MISTRAL_API_KEY
        response = httpx.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "pixtral-12b-2409",
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": f"data:image/png;base64,{img_b64}"
                        },
                        {
                            "type": "text",
                            "text": (
                                "Extrait le texte complet de ce document (BL ou facture). "
                                "Retourne uniquement le texte brut, ligne par ligne, "
                                "sans mise en forme ni commentaire."
                            )
                        }
                    ]
                }],
                "max_tokens": 2000,
            },
            timeout=30,
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Mistral Vision error page {page_number}: {e}")
        return None


def detect_line_type(text: str) -> tuple[str, str]:
    """
    Détecte le type d'une ligne et le code taxe éventuel.
    Retourne (line_type, tax_code)
    """
    if SECTOR_TAX_RE.search(text):
        # Extrait le code taxe
        match = SECTOR_TAX_RE.search(text)
        tax_code = match.group(0).upper() if match else ""
        return "sector_tax", tax_code

    if DISCOUNT_RE.search(text):
        return "discount", ""

    if SHIPPING_RE.search(text):
        return "shipping", ""

    return "product", ""


def parse_prices(text: str) -> list[Decimal]:
    """Extrait tous les montants d'une ligne."""
    prices = []
    for m in PRICE_RE.finditer(text):
        try:
            val = Decimal(m.group(1).replace(",", "."))
            prices.append(val)
        except InvalidOperation:
            pass
    return prices


def parse_quantity_unit(text: str) -> tuple[Optional[Decimal], str]:
    """Extrait quantité et unité d'une ligne."""
    m = QTY_RE.search(text)
    if m:
        try:
            qty = Decimal(m.group(1).replace(",", "."))
            unit = m.group(2).lower()
            return qty, unit
        except InvalidOperation:
            pass
    return None, ""


def parse_document_lines_via_llm(full_text: str) -> list[dict]:
    """
    Envoie le texte brut à Mistral pour extraction structurée des lignes.
    Retourne une liste de dicts normalisés.
    """
    import httpx
    from django.conf import settings

    prompt = f"""Tu es un assistant spécialisé dans l'analyse de factures et bons de livraison français.

    Analyse ce texte et extrais UNIQUEMENT les lignes de produits/services facturés.

    IGNORE absolument :
    - Les en-têtes de colonnes (Référence, Désignation, Quantité, Prix unitaire...)
    - Les adresses, téléphones, emails, sites web
    - Les coordonnées bancaires (IBAN, BIC...)
    - Les totaux, sous-totaux, montants TVA
    - Les numéros de client, de commande
    - Les mentions légales
    - Les lignes contenant uniquement des chiffres sans contexte produit
    - Les lignes de moins de 5 caractères

    INCLUS uniquement :
    - Les lignes de produits avec une désignation claire
    - Les taxes filière viande (CVO, INAPORC, INTERBEV, IP3, IP3V, IP5, RSD, TEO)
    - Les remises commerciales
    - Les promotions
    - Les produits gratuits
    - Les frais de port

    Pour chaque ligne retourne :
    - raw_label : désignation du produit (string, max 200 chars)
    - line_type : "product" | "sector_tax" | "discount" | "shipping" | "other"
    - tax_code : code taxe si sector_tax, sinon ""
    - quantity : quantité numérique ou null
    - unit : unité ("kg", "pièce", "colis", "litre"...) ou ""
    - unit_price_ht : prix unitaire HT numérique ou null
    - total_ht : total HT de la ligne numérique ou null

    Retourne UNIQUEMENT un tableau JSON valide, sans texte avant ou après.

    Texte :
    {full_text[:6000]}
    """

    try:
        api_key = settings.MISTRAL_API_KEY
        response = httpx.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model":       "mistral-small-latest",
                "messages":    [{"role": "user", "content": prompt}],
                "max_tokens":  3000,
                "temperature": 0.0,
            },
            timeout=30,
        )
        data     = response.json()
        content  = data["choices"][0]["message"]["content"].strip()

        # Nettoie les backticks markdown si présents
        content = content.replace("```json", "").replace("```", "").strip()

        import json
        items = json.loads(content)

        # Normalise et ajoute l'ordre
        lines = []
        for i, item in enumerate(items):
            lines.append({
                "raw_label":     item.get("raw_label", "")[:300],
                "line_type":     item.get("line_type", "product"),
                "tax_code":      item.get("tax_code", ""),
                "quantity":      _to_decimal(item.get("quantity")),
                "unit":          item.get("unit", ""),
                "unit_price_ht": _to_decimal(item.get("unit_price_ht")),
                "total_ht":      _to_decimal(item.get("total_ht")),
                "order":         i,
            })
        return lines

    except Exception as e:
        logger.error(f"Mistral parsing error: {e}")
        # Fallback sur le parser regex
        return parse_document_lines_via_llm(full_text)


def _to_decimal(value) -> Optional[Decimal]:
    """Convertit une valeur en Decimal, retourne None si impossible."""
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        return None


def match_ingredients(lines: list[dict], tenant_ingredients: list) -> list[dict]:
    """
    Matching fuzzy entre les libellés OCR et les ingrédients de la BDD.
    Utilise rapidfuzz avec score de confiance.

    tenant_ingredients : liste de (pk, name, supplier_refs)
    """
    if not tenant_ingredients:
        return lines

    # Prépare les noms pour le matching
    ingredient_names = [ing["name"] for ing in tenant_ingredients]

    for line in lines:
        if line["line_type"] != "product":
            continue

        # Nettoie le libellé pour le matching
        clean_label = re.sub(r'\d+[.,]\d+', '', line["raw_label"])  # retire les chiffres
        clean_label = re.sub(r'\b(kg|g|l|pce|pc|bt|col)\b', '', clean_label, flags=re.IGNORECASE)
        clean_label = clean_label.strip()

        if len(clean_label) < 3:
            continue

        # Matching fuzzy — token_sort_ratio gère les mots dans un ordre différent
        result = process.extractOne(
            clean_label,
            ingredient_names,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=40,  # seuil minimum 40%
        )

        if result:
            matched_name, score, idx = result
            line["matched_ingredient_pk"]   = tenant_ingredients[idx]["pk"]
            line["matched_ingredient_name"] = matched_name
            line["match_score"]             = score
        else:
            line["matched_ingredient_pk"]   = None
            line["matched_ingredient_name"] = None
            line["match_score"]             = None

    return lines


def process_document(document_instance) -> dict:
    """
    Fonction principale — traite un DeliveryDocument.
    Retourne un dict avec les lignes parsées et enrichies.
    """
    from apps.catalog.models import Ingredient
    from apps.purchasing.models import SupplierIngredient

    filepath = document_instance.document.path
    tenant   = document_instance.tenant

    # ── 1. Extraction texte ───────────────────────────────────────────────
    pages     = extract_text_from_pdf(filepath)
    full_text = ""
    engine    = "pymupdf"

    for page in pages:
        if page["has_text"]:
            full_text += page["text"] + "\n"
        else:
            logger.info(f"Page {page['page']} sans texte natif — fallback Mistral Vision")
            mistral_text = extract_text_via_mistral(filepath, page["page"])
            if mistral_text:
                full_text += mistral_text + "\n"
                engine = "mistral_vision"

    if not full_text.strip():
        return {"error": "Impossible d'extraire le texte du document.", "lines": []}

    # ── 2. Parsing lignes ─────────────────────────────────────────────────
    parsed_lines = parse_document_lines_via_llm(full_text)

    # ── 3. Récupère les ingrédients du tenant pour le matching ────────────
    # Priorise les références fournisseur si le fournisseur est connu
    tenant_ingredients = []

    if document_instance.supplier:
        # Références fournisseur en premier (plus fiables)
        supplier_refs = SupplierIngredient.objects.filter(
            supplier=document_instance.supplier,
            is_active=True,
        ).select_related("ingredient")

        for ref in supplier_refs:
            tenant_ingredients.append({
                "pk":   ref.ingredient.pk,
                "name": ref.supplier_item_name or ref.ingredient.name,
            })

    # Complète avec tous les ingrédients actifs du tenant
    existing_pks = {i["pk"] for i in tenant_ingredients}
    all_ingredients = Ingredient.objects.filter(is_active=True)
    for ing in all_ingredients:
        if ing.pk not in existing_pks:
            tenant_ingredients.append({"pk": ing.pk, "name": ing.name})

    # ── 4. Matching fuzzy ─────────────────────────────────────────────────
    matched_lines = match_ingredients(parsed_lines, tenant_ingredients)

    return {
        "lines":  matched_lines,
        "engine": engine,
        "pages":  len(pages),
        "error":  None,
    }