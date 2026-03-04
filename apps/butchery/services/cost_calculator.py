"""
Calcul du prix de revient par la méthode des coûts joints (joint cost allocation).

Formule :
  PV_HT(pièce)     = PV_TTC(pièce) / (1 + TVA)
  CA_total_HT      = Σ PV_HT(pièce) × poids(pièce)  [pièces valorisées]
  taux_marge_global = marge_totale_HT / CA_total_HT
  Nouveau_PA(pièce) = PV_HT(pièce) × (1 - taux_marge_global)

  marge_totale_HT  = CA_total_HT - coût_total_HT
  coût_total_HT    = achat + taxes_filière + prestation_externe
"""
from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
TWO  = Decimal("0.0001")  # précision 4 décimales


def calculate_session_costs(session) -> dict:
    """
    Calcule les prix de revient de toutes les pièces d'une session.
    Retourne un dict avec les résultats et met à jour les ButcheryLine.

    Étapes :
    1. Récupère toutes les lignes valorisées (ingredient, sellable, byproduct_sold)
    2. Calcule CA_total_HT théorique
    3. Calcule taux_marge_global
    4. Attribue Nouveau_PA à chaque pièce
    5. Met à jour session (rendement, coût moyen, marge)
    6. Crée/met à jour YieldRecord
    """
    from apps.butchery.models import ButcheryLine, YieldRecord

    coût_total = session.total_cost_ht

    if coût_total <= ZERO:
        return {"error": "Coût total nul — impossible de calculer."}

    # ── 1. Lignes valorisées ──────────────────────────────────────────────
    valorized_lines = session.lines.filter(
        output_type__in=["ingredient", "sellable"],
        selling_price_ttc__isnull=False,
        real_weight_kg__isnull=False,
        is_confirmed=True,
    )

    # Sous-produits vendus
    byproduct_lines = session.lines.filter(
        output_type="byproduct",
        byproduct_sold=True,
        byproduct_selling_price__isnull=False,
        real_weight_kg__isnull=False,
        is_confirmed=True,
    )

    # Déchets et pertes
    waste_lines = session.lines.filter(
        output_type__in=["waste", "byproduct"],
        is_confirmed=True,
    ).exclude(
        output_type="byproduct",
        byproduct_sold=True,
    )

    if not valorized_lines.exists():
        return {"error": "Aucune pièce valorisée confirmée."}

    # ── 2. CA total HT théorique ──────────────────────────────────────────
    ca_total_ht = ZERO
    for line in valorized_lines:
        pv_ht = line.selling_price_ttc / (1 + line.vat_rate)
        ca_total_ht += pv_ht * line.real_weight_kg

    # Ajoute les sous-produits vendus au CA
    for line in byproduct_lines:
        pv_ht = line.byproduct_selling_price / (Decimal("1") + line.vat_rate)
        ca_total_ht += pv_ht * line.real_weight_kg

    if ca_total_ht <= ZERO:
        return {"error": "CA total nul — vérifiez les prix de vente."}

    # ── 3. Taux de marge global ───────────────────────────────────────────
    marge_totale_ht  = ca_total_ht - coût_total
    taux_marge_global = marge_totale_ht / ca_total_ht

    # ── 4. Nouveau PA par pièce ───────────────────────────────────────────
    results = []
    total_output_weight = ZERO

    for line in valorized_lines:
        pv_ht     = line.selling_price_ttc / (1 + line.vat_rate)
        nouveau_pa = pv_ht * (1 - taux_marge_global)
        total_cost_line = nouveau_pa * line.real_weight_kg
        ca_line = pv_ht * line.real_weight_kg

        line.cost_per_kg    = nouveau_pa.quantize(TWO, ROUND_HALF_UP)
        line.total_cost     = total_cost_line.quantize(Decimal("0.01"), ROUND_HALF_UP)
        line.theoretical_ca = ca_line.quantize(Decimal("0.01"), ROUND_HALF_UP)
        line.save(update_fields=["cost_per_kg", "total_cost", "theoretical_ca"])

        total_output_weight += line.real_weight_kg
        results.append({
            "name":        line.name,
            "weight_kg":   float(line.real_weight_kg),
            "pv_ttc":      float(line.selling_price_ttc),
            "pv_ht":       float(pv_ht.quantize(Decimal("0.01"))),
            "cost_per_kg": float(line.cost_per_kg),
            "total_cost":  float(line.total_cost),
            "ca":          float(line.theoretical_ca),
            "margin":      float((ca_line - total_cost_line).quantize(Decimal("0.01"))),
            "margin_rate": float(taux_marge_global),
        })

    # Sous-produits vendus
    for line in byproduct_lines:
        pv_ht      = line.byproduct_selling_price / (Decimal("1") + line.vat_rate)
        nouveau_pa = pv_ht * (1 - taux_marge_global)
        line.cost_per_kg = nouveau_pa.quantize(TWO, ROUND_HALF_UP)
        line.total_cost  = (nouveau_pa * line.real_weight_kg).quantize(Decimal("0.01"))
        line.save(update_fields=["cost_per_kg", "total_cost"])
        total_output_weight += line.real_weight_kg

    # ── 5. Poids pertes ───────────────────────────────────────────────────
    total_waste = ZERO
    for line in waste_lines:
        total_waste += line.real_weight_kg

    # ── 6. Mise à jour session ────────────────────────────────────────────
    avg_cost = coût_total / total_output_weight if total_output_weight > ZERO else None
    yield_pct = (total_output_weight / session.purchase_weight_kg * 100
                 if session.purchase_weight_kg > ZERO else None)

    session.total_output_weight_kg = total_output_weight.quantize(Decimal("0.001"))
    session.total_waste_kg         = total_waste.quantize(Decimal("0.001"))
    session.real_yield_pct         = yield_pct.quantize(Decimal("0.01")) if yield_pct else None
    session.avg_cost_per_kg        = avg_cost.quantize(TWO) if avg_cost else None
    session.global_margin_rate     = (taux_marge_global * 100).quantize(Decimal("0.01"))
    session.status                 = "validated"
    session.save(update_fields=[
        "total_output_weight_kg", "total_waste_kg", "real_yield_pct",
        "avg_cost_per_kg", "global_margin_rate", "status",
    ])

    # ── 7. YieldRecord ────────────────────────────────────────────────────
    yields_data = {r["name"]: r for r in results}
    YieldRecord.objects.update_or_create(
        session=session,
        defaults={
            "template":             session.template,
            "supplier":             session.delivery_line.document.supplier
                                    if session.delivery_line else None,
            "session_date":         session.session_date,
            "purchase_weight_kg":   session.purchase_weight_kg,
            "purchase_price_per_kg": session.purchase_price_per_kg,
            "total_cost_ht":        coût_total,
            "global_yield_pct":     yield_pct or ZERO,
            "waste_pct":            (total_waste / session.purchase_weight_kg * 100
                                     if session.purchase_weight_kg > ZERO else ZERO),
            "effective_cost_per_kg": avg_cost or ZERO,
            "global_margin_rate":   taux_marge_global * 100,
            "yields_data":          yields_data,
        }
    )

    return {
        "error":              None,
        "taux_marge_global":  float(taux_marge_global),
        "ca_total_ht":        float(ca_total_ht),
        "cout_total_ht":      float(coût_total),
        "marge_totale_ht":    float(marge_totale_ht),
        "total_output_kg":    float(total_output_weight),
        "total_waste_kg":     float(total_waste),
        "yield_pct":          float(yield_pct) if yield_pct else None,
        "avg_cost_per_kg":    float(avg_cost) if avg_cost else None,
        "lines":              results,
    }