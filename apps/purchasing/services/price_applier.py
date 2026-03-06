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
    Crée un StockBatch + StockMovement pour alimenter le stock.
    Retourne un résumé des changements.
    """
    from apps.pricing.models import PriceRecord
    from apps.purchasing.models import Reception, ReceptionLine
    from apps.stock.models import StockBatch, StockMovement

    tenant   = document.tenant
    supplier = document.supplier
    today    = timezone.localdate()

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
            old_price = (
                PriceRecord.objects
                .filter(ingredient=ingredient, channel="purchase", valid_from__lte=today)
                .order_by("-valid_from")
                .values_list("price_ht", flat=True)
                .first()
            )

            PriceRecord.objects.create(
                tenant=tenant,
                ingredient=ingredient,
                channel="purchase",
                price_ht=line.unit_price_ht,
                valid_from=document.document_date or today,
                source="ocr_bl" if document.document_type == "bl" else "ocr_invoice",
                notes=f"Import auto — {document} — {line.raw_label[:80]}",
            )

            reception_line = ReceptionLine.objects.create(
                reception=reception,
                ingredient=ingredient,
                supplier_ref=None,
                invoiced_quantity=line.quantity or Decimal("1"),
                invoiced_price=line.unit_price_ht,
                invoiced_amount=round((line.unit_price_ht or 0) * (line.quantity or 1), 3),
            )

            line.reception_line = reception_line
            line.applied = True
            line.save(update_fields=["reception_line", "applied"])

            # ── Stock : lot + mouvement ───────────────────────────────────
            quantity = line.quantity or Decimal("1")
            unit     = line.unit or ingredient.use_unit or ingredient.purchase_unit or "kg"

            # Produit frais si conservation <= 8°C → DLC bloquante
            if (
                ingredient.target_keeping_temp_max is not None
                and ingredient.target_keeping_temp_max <= Decimal("8")
            ):
                date_type = "dlc"
            else:
                date_type = "dluo"

            batch = StockBatch.objects.create(
                company=company,
                ingredient=ingredient,
                recipe=None,
                reception_line=reception_line,
                quantity_initial=quantity,
                quantity_remaining=quantity,
                unit=unit,
                tracability_number=reception_line.tracability_number or "",
                best_before=reception_line.best_before,
                date_type=date_type,
                unit_price_at_entry=line.unit_price_ht,
            )

            StockMovement.objects.create(
                company=company,
                ingredient=ingredient,
                recipe=None,
                movement_type="reception",
                quantity=quantity,
                unit=unit,
                stock_batch=batch,
                reception_line=reception_line,
                notes=f"Réception {reception.reception_number} — {supplier}",
            )
            # ─────────────────────────────────────────────────────────────

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

    document.status = "validated"
    document.save(update_fields=["status"])

    return {
        "applied":   applied,
        "skipped":   skipped,
        "errors":    errors,
        "changes":   changes,
        "reception": reception,
    }