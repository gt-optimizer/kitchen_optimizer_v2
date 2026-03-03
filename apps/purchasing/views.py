import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string

from .models import Supplier, DeliveryDocument, DeliveryLine
from .forms import SupplierForm, DeliveryDocumentForm

logger = logging.getLogger(__name__)


# ── Fournisseurs ──────────────────────────────────────────────────────────────

@login_required
def supplier_list(request):
    suppliers = Supplier.objects.filter(tenant=request.tenant)
    return render(request, "purchasing/supplier_list.html", {
        "suppliers": suppliers,
    })


@login_required
def supplier_add(request):
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.tenant = request.tenant
            supplier.save()
            messages.success(request, f"Fournisseur « {supplier.name} » créé.")
            return redirect("purchasing:supplier_detail", pk=supplier.pk)
    else:
        form = SupplierForm()
    return render(request, "purchasing/supplier_form.html", {
        "form": form, "action": "Nouveau fournisseur"
    })


@login_required
def supplier_detail(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.tenant)
    documents = supplier.documents.order_by("-created_at")[:10]
    return render(request, "purchasing/supplier_detail.html", {
        "supplier": supplier, "documents": documents,
    })


@login_required
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, f"Fournisseur « {supplier.name} » mis à jour.")
            return redirect("purchasing:supplier_detail", pk=supplier.pk)
    else:
        form = SupplierForm(instance=supplier)
    return render(request, "purchasing/supplier_form.html", {
        "form": form, "action": "Modifier le fournisseur", "supplier": supplier,
    })


# ── Documents ─────────────────────────────────────────────────────────────────

@login_required
def document_list(request):
    documents = DeliveryDocument.objects.filter(
        tenant=request.tenant
    ).select_related("supplier").order_by("-created_at")
    return render(request, "purchasing/document_list.html", {
        "documents": documents,
    })


@login_required
def document_upload(request):
    if request.method == "POST":
        form = DeliveryDocumentForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.tenant = request.tenant
            doc.status = "pending"
            doc.save()
            messages.success(request, "Document uploadé — lancement de l'analyse OCR.")
            return redirect("purchasing:document_detail", pk=doc.pk)
        else:
            messages.error(request, "Erreur lors de l'upload.")
    else:
        form = DeliveryDocumentForm(tenant=request.tenant)

    steps_help = [
        (1, "fa-solid fa-file-arrow-up", ("Upload", "Glissez votre PDF ou sélectionnez-le")),
        (2, "fa-solid fa-magnifying-glass",
         ("Analyse OCR", "Le texte est extrait automatiquement. Les pages images passent par Mistral Vision.")),
        (3, "fa-solid fa-link", ("Matching", "Chaque ligne est associée à un ingrédient de votre catalogue.")),
        (4, "fa-solid fa-check", ("Validation", "Vérifiez les associations et confirmez. Les prix sont mis à jour.")),
    ]
    return render(request, "purchasing/document_upload.html", {
        "form": form, "steps_help": steps_help,
    })


@login_required
def document_detail(request, pk):
    doc   = get_object_or_404(DeliveryDocument, pk=pk, tenant=request.tenant)
    lines = doc.lines.select_related("matched_ingredient").order_by("order")

    from apps.catalog.models import Ingredient
    ingredients = Ingredient.objects.filter(
        is_active=True
    ).order_by("name").values("pk", "name")

    return render(request, "purchasing/document_detail.html", {
        "doc":         doc,
        "lines":       lines,
        "ingredients": ingredients,
    })


@login_required
def document_parse(request, pk):
    """Lance l'OCR + parsing + matching sur le document."""
    doc = get_object_or_404(DeliveryDocument, pk=pk, tenant=request.tenant)

    if request.method != "POST":
        return redirect("purchasing:document_detail", pk=pk)

    try:
        from .services.document_parser import process_document

        doc.status = "parsing"
        doc.save(update_fields=["status"])

        result = process_document(doc)

        if result.get("error"):
            doc.status = "error"
            doc.ocr_raw = {"error": result["error"]}
            doc.save(update_fields=["status", "ocr_raw"])
            messages.error(request, f"Erreur OCR : {result['error']}")
            return redirect("purchasing:document_detail", pk=pk)

        # Supprime les anciennes lignes si re-parse
        doc.lines.all().delete()

        # Crée les DeliveryLine
        from apps.catalog.models import Ingredient
        for line_data in result["lines"]:
            ingredient = None
            if line_data.get("matched_ingredient_pk"):
                ingredient = Ingredient.objects.filter(
                    pk=line_data["matched_ingredient_pk"]
                ).first()

            DeliveryLine.objects.create(
                document        = doc,
                line_type       = line_data["line_type"],
                order           = line_data["order"],
                raw_label       = line_data["raw_label"],
                quantity        = line_data.get("quantity"),
                unit            = line_data.get("unit", ""),
                unit_price_ht   = line_data.get("unit_price_ht"),
                total_ht        = line_data.get("total_ht"),
                matched_ingredient = ingredient,
                match_score     = line_data.get("match_score"),
                tax_code        = line_data.get("tax_code", ""),
            )

            from apps.purchasing.models import DeliveryLine as DL
            DL.objects.filter(
                document=doc,
                line_type="product",
                match_score__gte=85,
                matched_ingredient__isnull=False,
            ).update(match_confirmed=True)

        doc.status    = "parsed"
        doc.ocr_raw   = {"engine": result["engine"], "pages": result["pages"]}
        doc.ocr_engine = result["engine"]
        doc.save(update_fields=["status", "ocr_raw", "ocr_engine"])

        nb = len(result["lines"])
        messages.success(request, f"Document analysé — {nb} ligne(s) extraite(s) via {result['engine']}.")

    except Exception as e:
        logger.exception(f"Erreur parsing document {pk}: {e}")
        doc.status = "error"
        doc.save(update_fields=["status"])
        messages.error(request, f"Erreur inattendue : {e}")

    return redirect("purchasing:document_detail", pk=pk)


@login_required
def document_validate(request, pk):
    """Applique les prix des lignes confirmées."""
    doc = get_object_or_404(DeliveryDocument, pk=pk, tenant=request.tenant)

    if request.method != "POST":
        return redirect("purchasing:document_detail", pk=pk)

    from .services.price_applier import apply_document_prices
    result = apply_document_prices(doc)

    if result["applied"] > 0:
        changes_msg = ", ".join([
            f"{c['ingredient']} : {c['old_price'] or '—'} → {c['new_price']} €"
            + (f" ({c['delta_pct']:+.1f}%)" if c['delta_pct'] is not None else "")
            for c in result["changes"]
        ])
        messages.success(request, f"{result['applied']} prix appliqué(s). {changes_msg}")

    if result["skipped"]:
        messages.warning(request, f"{result['skipped']} ligne(s) ignorée(s).")

    return redirect("purchasing:document_detail", pk=pk)


@login_required
def document_line_confirm(request, pk, line_pk):
    """Confirme ou déconfirme le matching d'une ligne — HTMX."""
    line = get_object_or_404(DeliveryLine, pk=line_pk, document__pk=pk)
    if request.method == "POST":
        line.match_confirmed = not line.match_confirmed
        line.save(update_fields=["match_confirmed"])

    from apps.catalog.models import Ingredient

    ingredients = Ingredient.objects.filter(
        is_active=True
    ).order_by("name").values("pk", "name")

    html = render_to_string(
        "purchasing/partials/document_line_row.html",
        {"line": line, "doc": line.document, "ingredients": ingredients},
        request=request,
    )
    return HttpResponse(html)


@login_required
def document_line_match(request, pk, line_pk):
    """Modifie manuellement l'ingrédient associé à une ligne — HTMX."""
    line = get_object_or_404(DeliveryLine, pk=line_pk, document__pk=pk)
    if request.method == "POST":
        ingredient_pk = request.POST.get("ingredient_pk")
        if ingredient_pk:
            from apps.catalog.models import Ingredient
            ingredient = get_object_or_404(Ingredient, pk=ingredient_pk)
            line.matched_ingredient = ingredient
            line.match_score        = 100.0
            line.match_confirmed    = True
            line.save(update_fields=["matched_ingredient", "match_score", "match_confirmed"])

    from apps.catalog.models import Ingredient

    ingredients = Ingredient.objects.filter(
        is_active=True
    ).order_by("name").values("pk", "name")

    html = render_to_string(
        "purchasing/partials/document_line_row.html",
        {"line": line, "doc": line.document, "ingredients": ingredients},
        request=request,
    )
    return HttpResponse(html)