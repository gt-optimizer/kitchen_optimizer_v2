"""
Service d'application des prix après validation du document.
Met à jour PriceRecord et déclenche la propagation en cascade.
"""
import logging
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)


def apply_document_prices(document) -> dict:
    """
    Applique les prix des lignes confirmées d'un DeliveryDocument.
    Crée un PriceRecord par ingrédient + une Reception avec ses lignes.
    Retourne un résumé des changements.
    """
    from apps.pricing.models import PriceRecord
    from apps.purchasing.models import Reception, ReceptionLine

    tenant   = document.tenant
    supplier = document.supplier
    today    = timezone.localdate()

    # ── Récupère le site (company) du tenant ──────────────────────────────
    company = tenant.companies.first() if hasattr(tenant, 'companies') else None
    if not company:
        logger.error(f"apply_document_prices: aucun site (company) trouvé pour le tenant {tenant}")
        return {
            "applied":   0,
            "skipped":   0,
            "errors":    ["Aucun site configuré pour ce tenant — impossible de créer la réception."],
            "changes":   [],
            "reception": None,
        }

    confirmed_lines = document.lines.filter(
        line_type="product",
        match_confirmed=True,
        matched_ingredient__isnull=False,
        unit_price_ht__isnull=False,
        applied=False,
    ).select_related("matched_ingredient")

    if not confirmed_lines.exists():
        return {"applied": 0, "skipped": 0, "errors": [], "changes": [], "reception": None}

    # ── Crée la réception (une seule fois) ────────────────────────────────
    reception = Reception.objects.create(
        company=company,
        supplier=supplier,
        delivery_date=document.document_date or today,
        invoice_number=document.reference or "",
    )

    applied = 0
    skipped = 0
    errors  = []
    changes = []

    for line in confirmed_lines:
        ingredient = line.matched_ingredient
        try:
            # Prix précédent pour afficher le delta
            old_price = (
                PriceRecord.objects
                .filter(
                    ingredient=ingredient,
                    channel="purchase",
                    valid_from__lte=today,
                )
                .order_by("-valid_from")
                .values_list("price_ht", flat=True)
                .first()
            )

            # Crée le nouveau PriceRecord
            PriceRecord.objects.create(
                tenant=tenant,
                ingredient=ingredient,
                channel="purchase",
                price_ht=line.unit_price_ht,
                valid_from=document.document_date or today,
                source="ocr_bl" if document.document_type == "bl" else "ocr_invoice",
                notes=f"Import auto — {document} — {line.raw_label[:80]}",
            )

            # Crée la ligne de réception
            reception_line = ReceptionLine.objects.create(
                reception=reception,
                ingredient=ingredient,
                supplier_ref=None,
                invoiced_quantity=line.quantity or Decimal("1"),
                invoiced_price=line.unit_price_ht,
                invoiced_amount=round(
                    (line.unit_price_ht or 0) * (line.quantity or 1), 3
                ),
            )

            # Lie la ligne de livraison à la ligne de réception
            line.reception_line = reception_line
            line.applied = True
            line.save(update_fields=["reception_line", "applied"])

            # Calcule le delta prix
            delta     = None
            delta_pct = None
            if old_price:
                delta     = float(line.unit_price_ht) - float(old_price)
                delta_pct = round(delta / float(old_price) * 100, 1)

            changes.append({
                "ingredient": ingredient.name,
                "old_price":  float(old_price) if old_price else None,
                "new_price":  float(line.unit_price_ht),
                "delta":      delta,
                "delta_pct":  delta_pct,
            })

            applied += 1

        except Exception as e:
            logger.error(f"Erreur application prix {ingredient.name}: {e}")
            errors.append(f"{ingredient.name} : {e}")
            skipped += 1

    # Marque le document comme validé
    document.status = "validated"
    document.save(update_fields=["status"])

    return {
        "applied":   applied,
        "skipped":   skipped,
        "errors":    errors,
        "changes":   changes,
        "reception": reception,
    }