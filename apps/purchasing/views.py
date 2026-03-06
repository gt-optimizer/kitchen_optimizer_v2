import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.template.loader import render_to_string

from .models import Supplier, DeliveryDocument, DeliveryLine, SupplierIngredient, SupplierContact
from .forms import SupplierForm, DeliveryDocumentForm, SupplierIngredientForm, SupplierContactForm

logger = logging.getLogger(__name__)


# ── Fournisseurs — liste ───────────────────────────────────────────────────────

@login_required
def supplier_list(request):
    qs = Supplier.objects.filter(tenant=request.tenant)

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(city__icontains=q) |
            Q(siret__icontains=q) |
            Q(email__icontains=q)
        )

    active_filter = request.GET.get("active", "")
    if active_filter == "1":
        qs = qs.filter(is_active=True)
    elif active_filter == "0":
        qs = qs.filter(is_active=False)

    # HTMX — retourne uniquement les lignes du tableau
    if request.headers.get("HX-Request"):
        return render(request, "purchasing/partials/supplier_table_rows.html", {
            "suppliers": qs,
        })

    return render(request, "purchasing/supplier_list.html", {
        "suppliers": qs,
        "q": q,
        "active_filter": active_filter,
    })


# ── Fournisseurs — création ────────────────────────────────────────────────────

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
        "form": form,
        "action": "Nouveau fournisseur",
    })


# ── Fournisseurs — détail ──────────────────────────────────────────────────────

@login_required
def supplier_detail(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.tenant)
    contacts           = supplier.contacts.all().order_by("last_name", "first_name")
    supplier_ingredients = supplier.supplier_ingredients.select_related("ingredient").filter(is_active=True)
    receptions         = supplier.reception_set.order_by("-delivery_date")[:20] if hasattr(supplier, "reception_set") else []
    documents          = supplier.documents.order_by("-created_at")[:20]

    return render(request, "purchasing/supplier_detail.html", {
        "supplier":             supplier,
        "contacts":             contacts,
        "supplier_ingredients": supplier_ingredients,
        "receptions":           receptions,
        "documents":            documents,
    })


# ── Fournisseurs — édition ─────────────────────────────────────────────────────

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
        "form": form,
        "action": "Modifier le fournisseur",
        "supplier": supplier,
    })


# ══════════════════════════════════════════════════════════════════════════════
# CONTACTS — HTMX drawers
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def supplier_contact_add(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        form = SupplierContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.supplier = supplier
            contact.save()
            # Retourne la liste mise à jour pour HTMX
            contacts = supplier.contacts.all().order_by("last_name", "first_name")
            return render(request, "purchasing/partials/supplier_contacts.html", {
                "supplier": supplier,
                "contacts": contacts,
            })
        # Formulaire invalide — retourne le drawer avec erreurs
        return render(request, "purchasing/partials/supplier_contact_drawer.html", {
            "form": form,
            "supplier": supplier,
            "form_action": request.path,
        })
    else:
        form = SupplierContactForm()
    return render(request, "purchasing/partials/supplier_contact_drawer.html", {
        "form": form,
        "supplier": supplier,
        "form_action": request.path,
    })


@login_required
def supplier_contact_edit(request, pk, contact_pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.tenant)
    contact  = get_object_or_404(SupplierContact, pk=contact_pk, supplier=supplier)
    if request.method == "POST":
        form = SupplierContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            contacts = supplier.contacts.all().order_by("last_name", "first_name")
            return render(request, "purchasing/partials/supplier_contacts.html", {
                "supplier": supplier,
                "contacts": contacts,
            })
        return render(request, "purchasing/partials/supplier_contact_drawer.html", {
            "form": form,
            "supplier": supplier,
            "contact": contact,
            "form_action": request.path,
        })
    else:
        form = SupplierContactForm(instance=contact)
    return render(request, "purchasing/partials/supplier_contact_drawer.html", {
        "form": form,
        "supplier": supplier,
        "contact": contact,
        "form_action": request.path,
    })


@login_required
def supplier_contact_delete(request, pk, contact_pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.tenant)
    contact  = get_object_or_404(SupplierContact, pk=contact_pk, supplier=supplier)
    if request.method == "POST":
        contact.delete()
    contacts = supplier.contacts.all().order_by("last_name", "first_name")
    return render(request, "purchasing/partials/supplier_contacts.html", {
        "supplier": supplier,
        "contacts": contacts,
    })


# ══════════════════════════════════════════════════════════════════════════════
# RÉFÉRENCES INGRÉDIENTS — HTMX drawers
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def supplier_ingredient_add(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        form = SupplierIngredientForm(request.POST, tenant=request.tenant, supplier=supplier)
        if form.is_valid():
            si = form.save(commit=False)
            si.supplier = supplier
            si.save()
            sis = supplier.supplier_ingredients.select_related("ingredient").filter(is_active=True)
            return render(request, "purchasing/partials/supplier_ingredients.html", {
                "supplier": supplier,
                "supplier_ingredients": sis,
            })
        return render(request, "purchasing/partials/supplier_ingredient_drawer.html", {
            "form": form,
            "supplier": supplier,
            "form_action": request.path,
        })
    else:
        form = SupplierIngredientForm(tenant=request.tenant, supplier=supplier)
    return render(request, "purchasing/partials/supplier_ingredient_drawer.html", {
        "form": form,
        "supplier": supplier,
        "form_action": request.path,
    })


@login_required
def supplier_ingredient_edit(request, pk, si_pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.tenant)
    si       = get_object_or_404(SupplierIngredient, pk=si_pk, supplier=supplier)
    if request.method == "POST":
        form = SupplierIngredientForm(request.POST, instance=si, tenant=request.tenant)
        if form.is_valid():
            form.save()
            sis = supplier.supplier_ingredients.select_related("ingredient").filter(is_active=True)
            return render(request, "purchasing/partials/supplier_ingredients.html", {
                "supplier": supplier,
                "supplier_ingredients": sis,
            })
        return render(request, "purchasing/partials/supplier_ingredient_drawer.html", {
            "form": form,
            "supplier": supplier,
            "si": si,
            "form_action": request.path,
        })
    else:
        form = SupplierIngredientForm(instance=si, tenant=request.tenant)
    return render(request, "purchasing/partials/supplier_ingredient_drawer.html", {
        "form": form,
        "supplier": supplier,
        "si": si,
        "form_action": request.path,
    })


@login_required
def supplier_ingredient_delete(request, pk, si_pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.tenant)
    si       = get_object_or_404(SupplierIngredient, pk=si_pk, supplier=supplier)
    if request.method == "POST":
        si.delete()
    sis = supplier.supplier_ingredients.select_related("ingredient").filter(is_active=True)
    return render(request, "purchasing/partials/supplier_ingredients.html", {
        "supplier": supplier,
        "supplier_ingredients": sis,
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

        supplier_detection = result.get("supplier_detection", {})
        if not supplier_detection.get("found") and supplier_detection.get("extracted"):
            # Stocke les données extraites pour proposer la création
            doc.ocr_raw["supplier_extracted"] = supplier_detection["extracted"]
            doc.save(update_fields=["ocr_raw"])
            messages.warning(
                request,
                f"Fournisseur non reconnu dans votre base. "
                f"Consultez le document pour le créer."
            )

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
    line = get_object_or_404(DeliveryLine, pk=line_pk, document__pk=pk)
    if request.method == "POST":
        line.match_confirmed = not line.match_confirmed
        line.save(update_fields=["match_confirmed"])
        # Sauvegarde le mapping si confirmation
        if line.match_confirmed and line.matched_ingredient:
            _save_label_mapping(line, line.matched_ingredient, request.tenant)

    from apps.catalog.models import Ingredient
    ingredients = Ingredient.objects.filter(is_active=True).order_by("name").values("pk", "name")
    html = render_to_string(
        "purchasing/partials/document_line_row.html",
        {"line": line, "doc": line.document, "ingredients": ingredients},
        request=request,
    )
    return HttpResponse(html)


@login_required
def document_line_match(request, pk, line_pk):
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
            # Sauvegarde le mapping
            _save_label_mapping(line, ingredient, request.tenant)

    from apps.catalog.models import Ingredient
    ingredients = Ingredient.objects.filter(is_active=True).order_by("name").values("pk", "name")
    html = render_to_string(
        "purchasing/partials/document_line_row.html",
        {"line": line, "doc": line.document, "ingredients": ingredients},
        request=request,
    )
    return HttpResponse(html)


@login_required
def document_delete(request, pk):
    doc = get_object_or_404(DeliveryDocument, pk=pk, tenant=request.tenant)

    if request.method == "POST":
        label = str(doc)
        # Supprime le fichier physique si présent
        if doc.document:
            import os
            if os.path.isfile(doc.document.path):
                os.remove(doc.document.path)
        doc.delete()
        messages.success(request, f"Document « {label} » supprimé.")
        return redirect("purchasing:document_list")

    return render(request, "purchasing/document_confirm_delete.html", {"doc": doc})

@login_required
def supplier_add_from_doc(request, pk):
    doc = get_object_or_404(DeliveryDocument, pk=pk, tenant=request.tenant)
    extracted = doc.ocr_raw.get("supplier_extracted", {})

    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.tenant = request.tenant
            supplier.save()
            # Lie le fournisseur au document
            doc.supplier = supplier
            doc.save(update_fields=["supplier"])
            messages.success(request, f"Fournisseur « {supplier.name} » créé et lié au document.")
            return redirect("purchasing:document_detail", pk=doc.pk)
    else:
        # Pré-remplit le formulaire avec les données extraites
        form = SupplierForm(initial={
            "name":       extracted.get("name", ""),
            "address":    extracted.get("address", ""),
            "zipcode":    extracted.get("zipcode", ""),
            "city":       extracted.get("city", ""),
            "phone":      extracted.get("phone", ""),
            "email":      extracted.get("email", ""),
            "siret":      extracted.get("siret", ""),
            "rcs":        extracted.get("rcs", ""),
            "vat_number": extracted.get("vat_number", ""),
        })

    return render(request, "purchasing/supplier_form.html", {
        "form":    form,
        "action":  "Créer le fournisseur",
        "doc":     doc,
    })


def _save_label_mapping(line, ingredient, tenant):
    """Mémorise ou renforce le mapping libellé → ingrédient."""
    from .services.document_parser import _normalize_label
    from .models import SupplierLabelMapping

    normalized = _normalize_label(line.raw_label)
    if not normalized:
        return

    mapping, created = SupplierLabelMapping.objects.get_or_create(
        tenant=tenant,
        supplier=line.document.supplier,
        normalized_label=normalized,
        defaults={
            "raw_label":  line.raw_label,
            "ingredient": ingredient,
            "score":      1,
        }
    )
    if not created:
        # Renforce le score si même ingrédient
        if mapping.ingredient == ingredient:
            mapping.score = min(20, mapping.score + 1)
        else:
            # Ingrédient différent — corrige le mapping
            mapping.ingredient = ingredient
            mapping.score      = 1
            mapping.raw_label  = line.raw_label
        mapping.save()

@login_required
def ingredient_create_from_line(request, pk, line_pk):
    doc  = get_object_or_404(DeliveryDocument, pk=pk, tenant=request.tenant)
    line = get_object_or_404(DeliveryLine, pk=line_pk, document=doc)

    from apps.catalog.forms import IngredientForm

    if request.method == "POST":
        data = request.POST.copy()
        data.setdefault("net_weight_kg", "1")
        data.setdefault("net_volume_l", "1")
        data.setdefault("pieces_per_package", "1")
        data.setdefault("packages_per_purchase_unit", "1")
        data.setdefault("yield_rate", "100")
        form = IngredientForm(data, request.FILES)
        if not form.is_valid():
            print("ERREURS FORM:", form.errors)  # visible dans la console runserver
            print("ERREURS NON FIELD:", form.non_field_errors())
        if form.is_valid():
            ingredient = form.save(commit=False)
            ingredient.tenant = request.tenant
            ingredient.is_active = True
            ingredient.save()

            if doc.supplier:
                from apps.purchasing.models import SupplierIngredient
                SupplierIngredient.objects.get_or_create(
                    supplier=doc.supplier,
                    ingredient=ingredient,
                    defaults={
                        "supplier_item_name": line.raw_label[:100],
                        "negotiated_price":   line.unit_price_ht or 0,
                        "is_preferred":       True,
                    }
                )

            line.matched_ingredient = ingredient
            line.match_score        = 100.0
            line.match_confirmed    = True
            line.save(update_fields=["matched_ingredient", "match_score", "match_confirmed"])

            _save_label_mapping(line, ingredient, request.tenant)

            if line.unit_price_ht:
                from apps.pricing.models import PriceRecord
                from django.utils import timezone
                PriceRecord.objects.create(
                    tenant     = request.tenant,
                    ingredient = ingredient,
                    channel    = "purchase",
                    price_ht   = line.unit_price_ht,
                    valid_from = doc.document_date or timezone.localdate(),
                    source     = "ocr_bl",
                    notes      = f"Créé depuis {doc}",
                )

            messages.success(request, f"Ingrédient « {ingredient.name} » créé et associé.")
            return redirect("purchasing:document_detail", pk=doc.pk)

    else:
        form = IngredientForm(initial={
            "name":          line.raw_label[:100],
            "purchase_unit": line.unit or "pièce",
            "use_unit":      line.unit or "pièce",
        })

    return render(request, "purchasing/ingredient_create_from_line.html", {
        "form": form,
        "line": line,
        "doc":  doc,
    })