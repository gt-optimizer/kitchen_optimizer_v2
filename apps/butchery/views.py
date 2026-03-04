import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string

from .models import CarcassTemplate, CarcassTemplateLine, ButcherySession, ButcheryLine, YieldRecord
from .forms import CarcassTemplateForm, CarcassTemplateLineForm, ButcherySessionForm, ButcheryLineForm

logger = logging.getLogger(__name__)


# ── Gabarits ──────────────────────────────────────────────────────────────────

@login_required
def template_list(request):
    templates = CarcassTemplate.objects.filter(tenant=request.tenant)
    return render(request, "butchery/template_list.html", {
        "templates": templates,
    })


@login_required
def template_add(request):
    if request.method == "POST":
        form = CarcassTemplateForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.tenant = request.tenant
            t.save()
            messages.success(request, f"Gabarit « {t.name} » créé.")
            return redirect("butchery:template_detail", pk=t.pk)
    else:
        form = CarcassTemplateForm()
    return render(request, "butchery/template_form.html", {
        "form": form, "action": "Nouveau gabarit",
    })


@login_required
def template_detail(request, pk):
    template = get_object_or_404(CarcassTemplate, pk=pk, tenant=request.tenant)
    # Construit l'arbre des lignes
    root_lines = template.lines.filter(parent__isnull=True).order_by("order")
    return render(request, "butchery/template_detail.html", {
        "template":   template,
        "root_lines": root_lines,
    })


@login_required
def template_edit(request, pk):
    template = get_object_or_404(CarcassTemplate, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        form = CarcassTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, "Gabarit mis à jour.")
            return redirect("butchery:template_detail", pk=template.pk)
    else:
        form = CarcassTemplateForm(instance=template)
    return render(request, "butchery/template_form.html", {
        "form": form, "action": "Modifier le gabarit", "template": template,
    })


@login_required
def template_line_add(request, pk):
    template = get_object_or_404(CarcassTemplate, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        form = CarcassTemplateLineForm(request.POST, template=template)
        if form.is_valid():
            line = form.save(commit=False)
            line.template = template
            line.save()
            if request.headers.get("HX-Request"):
                root_lines = template.lines.filter(parent__isnull=True).order_by("order")
                html = render_to_string(
                    "butchery/partials/template_lines_tree.html",
                    {"template": template, "root_lines": root_lines},
                    request=request,
                )
                return HttpResponse(html)
            return redirect("butchery:template_detail", pk=pk)
    else:
        # Pré-sélectionne le parent si passé en GET
        parent_pk = request.GET.get("parent")
        initial = {"parent": parent_pk} if parent_pk else {}
        form = CarcassTemplateLineForm(template=template, initial=initial)
    return render(request, "butchery/template_line_form.html", {
        "form": form, "template": template, "action": "Ajouter une pièce",
    })


@login_required
def template_line_edit(request, pk, line_pk):
    template = get_object_or_404(CarcassTemplate, pk=pk, tenant=request.tenant)
    line     = get_object_or_404(CarcassTemplateLine, pk=line_pk, template=template)
    if request.method == "POST":
        form = CarcassTemplateLineForm(request.POST, instance=line, template=template)
        if form.is_valid():
            form.save()
            return redirect("butchery:template_detail", pk=pk)
    else:
        form = CarcassTemplateLineForm(instance=line, template=template)
    return render(request, "butchery/template_line_form.html", {
        "form": form, "template": template, "line": line, "action": "Modifier la pièce",
    })


@login_required
def template_line_delete(request, pk, line_pk):
    template = get_object_or_404(CarcassTemplate, pk=pk, tenant=request.tenant)
    line     = get_object_or_404(CarcassTemplateLine, pk=line_pk, template=template)
    if request.method == "POST":
        line.delete()
        messages.success(request, f"Pièce « {line.name} » supprimée.")
    return redirect("butchery:template_detail", pk=pk)


# ── Sessions ──────────────────────────────────────────────────────────────────

@login_required
def session_list(request):
    sessions = ButcherySession.objects.filter(
        tenant=request.tenant
    ).select_related("template").order_by("-session_date")
    return render(request, "butchery/session_list.html", {
        "sessions": sessions,
    })


@login_required
def session_add(request):
    if request.method == "POST":
        form = ButcherySessionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            session = form.save(commit=False)
            session.tenant = request.tenant
            # Calcule purchase_total_ht automatiquement
            session.purchase_total_ht = (
                session.purchase_weight_kg * session.purchase_price_per_kg
            )
            session.save()
            # Si un gabarit est choisi, pré-remplit les lignes
            if session.template:
                _prefill_lines_from_template(session)
            messages.success(request, f"Session « {session.description} » créée.")
            return redirect("butchery:session_detail", pk=session.pk)
    else:
        form = ButcherySessionForm(tenant=request.tenant)
    return render(request, "butchery/session_form.html", {
        "form": form, "action": "Nouvelle session de découpe",
    })


@login_required
def session_edit(request, pk):
    session = get_object_or_404(ButcherySession, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        form = ButcherySessionForm(request.POST, instance=session, tenant=request.tenant)
        if form.is_valid():
            session = form.save(commit=False)
            session.purchase_total_ht = (
                session.purchase_weight_kg * session.purchase_price_per_kg
            )
            session.save()
            messages.success(request, "Session mise à jour.")
            return redirect("butchery:session_detail", pk=session.pk)
    else:
        form = ButcherySessionForm(instance=session, tenant=request.tenant)
    return render(request, "butchery/session_form.html", {
        "form": form, "action": "Modifier la session", "session": session,
    })


@login_required
def session_detail(request, pk):
    session    = get_object_or_404(ButcherySession, pk=pk, tenant=request.tenant)
    root_lines = session.lines.filter(
        parent_line__isnull=True
    ).order_by("order", "created_at")
    line_form  = ButcheryLineForm(session=session)
    return render(request, "butchery/session_detail.html", {
        "session":    session,
        "root_lines": root_lines,
        "line_form":  line_form,
    })


@login_required
def session_close(request, pk):
    """Marque la session comme terminée — prête pour le calcul."""
    session = get_object_or_404(ButcherySession, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        session.status = "completed"
        session.save(update_fields=["status"])
        messages.success(request, "Session terminée — vous pouvez maintenant calculer les prix.")
    return redirect("butchery:session_detail", pk=pk)


@login_required
def session_validate(request, pk):
    """Lance le calcul des prix de revient."""
    session = get_object_or_404(ButcherySession, pk=pk, tenant=request.tenant)
    if request.method != "POST":
        return redirect("butchery:session_detail", pk=pk)

    from .services.cost_calculator import calculate_session_costs
    result = calculate_session_costs(session)

    if result.get("error"):
        messages.error(request, f"Erreur calcul : {result['error']}")
    else:
        messages.success(
            request,
            f"Prix calculés — {len(result['lines'])} pièces. "
            f"Taux de marge : {result['taux_marge_global']*100:.1f}% | "
            f"Rendement : {result['yield_pct']:.1f}%"
        )
        # Propage les prix vers PriceRecord
        _propagate_prices_to_catalog(session)

    return redirect("butchery:session_detail", pk=pk)


@login_required
def session_line_add(request, pk):
    session = get_object_or_404(ButcherySession, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        data = request.POST.copy()
        data.setdefault("vat_rate", "0.0550")
        data.setdefault("order", "0")
        form = ButcheryLineForm(data, session=session)
        print("ERRORS:", form.errors)
        if form.is_valid():
            line = form.save(commit=False)
            line.session = session
            line.save()
            if request.headers.get("HX-Request"):
                root_lines = session.lines.filter(
                    parent_line__isnull=True
                ).order_by("order", "created_at")
                html = render_to_string(
                    "butchery/partials/session_lines_table.html",
                    {"session": session, "root_lines": root_lines},
                    request=request,
                )
                return HttpResponse(html)
            return redirect("butchery:session_detail", pk=pk)
    else:
        form = ButcheryLineForm(session=session)
    return render(request, "butchery/session_line_form.html", {
        "form": form, "session": session, "action": "Ajouter une pièce",
    })


@login_required
def session_line_edit(request, pk, line_pk):
    session = get_object_or_404(ButcherySession, pk=pk, tenant=request.tenant)
    line    = get_object_or_404(ButcheryLine, pk=line_pk, session=session)
    if request.method == "POST":
        form = ButcheryLineForm(request.POST, instance=line, session=session)
        print("ERRORS:", form.errors)
        if form.is_valid():
            form.save()
            return redirect("butchery:session_detail", pk=pk)
    else:
        form = ButcheryLineForm(instance=line, session=session)
    return render(request, "butchery/session_line_form.html", {
        "form": form, "session": session, "line": line, "action": "Modifier la pièce",
    })


@login_required
def session_line_delete(request, pk, line_pk):
    session = get_object_or_404(ButcherySession, pk=pk, tenant=request.tenant)
    line    = get_object_or_404(ButcheryLine, pk=line_pk, session=session)
    if request.method == "POST":
        name = line.name
        line.delete()
        if request.headers.get("HX-Request"):
            root_lines = session.lines.filter(
                parent_line__isnull=True
            ).order_by("order", "created_at")
            html = render_to_string(
                "butchery/partials/session_lines_table.html",
                {"session": session, "root_lines": root_lines},
                request=request,
            )
            return HttpResponse(html)
        messages.success(request, f"Pièce « {name} » supprimée.")
    return redirect("butchery:session_detail", pk=pk)


@login_required
def session_line_confirm(request, pk, line_pk):
    """Confirme/déconfirme une pesée — HTMX."""
    session = get_object_or_404(ButcherySession, pk=pk, tenant=request.tenant)
    line    = get_object_or_404(ButcheryLine, pk=line_pk, session=session)
    if request.method == "POST":
        line.is_confirmed = not line.is_confirmed
        line.save(update_fields=["is_confirmed"])
    html = render_to_string(
        "butchery/partials/session_line_row.html",
        {"line": line, "session": session},
        request=request,
    )
    return HttpResponse(html)


# ── Historique rendements ─────────────────────────────────────────────────────

@login_required
def yield_list(request):
    records = YieldRecord.objects.filter(
        session__tenant=request.tenant
    ).select_related("template", "supplier").order_by("-session_date")
    return render(request, "butchery/yield_list.html", {
        "records": records,
    })


@login_required
def yield_detail(request, pk):
    record = get_object_or_404(YieldRecord, pk=pk, session__tenant=request.tenant)
    return render(request, "butchery/yield_detail.html", {
        "record": record,
    })


# ── Helpers privés ────────────────────────────────────────────────────────────

def _prefill_lines_from_template(session):
    """Pré-remplit les lignes d'une session depuis le gabarit."""
    def create_lines(template_lines, parent_line=None, order_start=0):
        for i, tl in enumerate(template_lines):
            line = ButcheryLine.objects.create(
                session       = session,
                parent_line   = parent_line,
                template_line = tl,
                name          = tl.name,
                output_type   = tl.output_type,
                real_weight_kg = 0,
                selling_price_ttc = tl.selling_price_ttc,
                vat_rate       = tl.vat_rate,
                linked_ingredient = tl.linked_ingredient,
                order          = order_start + i,
            )
            # Récursif — crée les sous-lignes
            children = tl.children.order_by("order")
            if children.exists():
                create_lines(children, parent_line=line, order_start=0)

    root_lines = session.template.lines.filter(
        parent__isnull=True
    ).order_by("order")
    create_lines(root_lines)


def _propagate_prices_to_catalog(session):
    """Propage les prix de revient calculés vers PriceRecord."""
    from apps.pricing.models import PriceRecord
    from django.utils import timezone

    updated = 0
    for line in session.lines.filter(
        cost_per_kg__isnull=False,
        linked_ingredient__isnull=False,
    ):
        PriceRecord.objects.create(
            tenant     = session.tenant,
            ingredient = line.linked_ingredient,
            channel    = "purchase",
            price_ht   = line.cost_per_kg,
            valid_from = session.session_date,
            source     = "butchery",
            notes      = f"Calculé depuis session {session}",
        )
        updated += 1

    logger.info(f"Session {session.pk} : {updated} PriceRecord créés.")