"""
Vues de l'app stock.

URLs couvertes :
  stock/                         → stock_dashboard
  stock/batches/                 → batch_list
  stock/batches/<pk>/edit/       → batch_edit
  stock/movements/               → movement_list
  stock/corrections/add/         → correction_add (HTMX)
  stock/inventories/             → inventory_list
  stock/inventories/add/         → inventory_create
  stock/inventories/<pk>/        → inventory_detail
  stock/inventories/<pk>/validate/ → inventory_validate
  stock/inventories/<pk>/lines/<lpk>/edit/ → inventory_line_edit (HTMX)
  stock/transfers/               → transfer_list
  stock/transfers/add/           → transfer_create
  stock/transfers/<pk>/          → transfer_detail
  stock/transfers/<pk>/send/     → transfer_send
  stock/transfers/<pk>/receive/  → transfer_receive
  stock/transfers/<pk>/lines/add/ → transfer_line_add (HTMX)
  stock/transfers/<pk>/lines/<lpk>/delete/ → transfer_line_delete (HTMX)
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils.timezone import localdate, now
from django.db.models import Q, Sum

from apps.company.mixins import require_role, get_current_company
from .models import (
    StockBatch, StockLevel, StockMovement,
    Inventory, InventoryLine,
    InternalTransfer, InternalTransferLine,
)
from .forms import (
    StockCorrectionForm, StockBatchEditForm,
    InventoryForm, InventoryLineForm,
    InternalTransferForm, InternalTransferLineForm,
)


def _get_company(request):
    return get_current_company(request)


# ── Dashboard ──────────────────────────────────────────────────────────────────

@login_required
@require_role('owner', 'admin', 'production', 'worker')
def stock_dashboard(request):
    company = _get_company(request)
    print("DEBUG company:", company, "| pk:", company.pk if company else None)

    today   = localdate()

    # Niveaux de stock
    levels = StockLevel.objects.filter(company=company).select_related(
        'ingredient', 'recipe'
    ).order_by('ingredient__name', 'recipe__name')

    # Alertes DLC (lots qui expirent dans <= 3 jours)
    from datetime import timedelta
    dlc_warnings = StockBatch.objects.filter(
        company=company,
        is_depleted=False,
        best_before__isnull=False,
        best_before__lte=today + timedelta(days=3),
    ).select_related('ingredient', 'recipe').order_by('best_before')

    # Stocks sous le minimum
    low_stock = [l for l in levels if l.is_below_minimum]

    # Inventaire en cours
    current_inventory = Inventory.objects.filter(
        company=company, status='draft'
    ).first()

    context = {
        'company':           company,
        'levels':            levels,
        'dlc_warnings':      dlc_warnings,
        'low_stock':         low_stock,
        'current_inventory': current_inventory,
        'today':             today,
    }
    return render(request, 'stock/dashboard.html', context)


# ── Lots ───────────────────────────────────────────────────────────────────────

@login_required
@require_role('owner', 'admin', 'production', 'worker')
def batch_list(request):
    company = _get_company(request)
    today   = localdate()

    batches = StockBatch.objects.filter(
        company=company, is_depleted=False
    ).select_related('ingredient', 'recipe', 'storage_place').order_by(
        'ingredient__name', 'recipe__name', 'best_before'
    )

    # Filtres
    search = request.GET.get('q', '')
    if search:
        batches = batches.filter(
            Q(ingredient__name__icontains=search) |
            Q(recipe__name__icontains=search) |
            Q(tracability_number__icontains=search)
        )

    filter_type = request.GET.get('filter', '')
    if filter_type == 'expired':
        batches = batches.filter(best_before__lt=today)
    elif filter_type == 'warning':
        from datetime import timedelta
        batches = batches.filter(best_before__lte=today + timedelta(days=3))
    elif filter_type == 'no_date':
        batches = batches.filter(best_before__isnull=True)

    if request.headers.get('HX-Request'):
        return render(request, 'stock/partials/batch_table.html', {
            'batches': batches, 'today': today
        })

    return render(request, 'stock/batch_list.html', {
        'company': company, 'batches': batches,
        'today': today, 'search': search, 'filter_type': filter_type,
    })


@login_required
@require_role('owner', 'admin', 'production')
def batch_edit(request, pk):
    company = _get_company(request)
    batch   = get_object_or_404(StockBatch, pk=pk, company=company)
    if request.method == 'POST':
        form = StockBatchEditForm(request.POST, instance=batch, company=company)
        if form.is_valid():
            form.save()
            if request.headers.get('HX-Request'):
                return render(request, 'stock/partials/batch_row.html', {
                    'batch': batch, 'today': localdate()
                })
            messages.success(request, "Lot mis à jour.")
            return redirect('stock:batch_list')
    else:
        form = StockBatchEditForm(instance=batch, company=company)

    return render(request, 'stock/partials/batch_edit_drawer.html', {
        'form': form, 'batch': batch,
        'form_action': request.path,
    })


# ── Mouvements ─────────────────────────────────────────────────────────────────

@login_required
@require_role('owner', 'admin', 'production', 'worker')
def movement_list(request):
    company   = _get_company(request)
    movements = StockMovement.objects.filter(company=company).select_related(
        'ingredient', 'recipe'
    )[:200]

    return render(request, 'stock/movement_list.html', {
        'company': company, 'movements': movements,
    })


@login_required
@require_role('owner', 'admin', 'production', 'worker')
def correction_add(request):
    """
    Correction manuelle (perte, casse, don...).
    Accessible depuis le dashboard et la liste des lots.
    """
    company = _get_company(request)

    # Lot pré-sélectionné via GET ?batch=<pk>
    batch    = None
    batch_pk = request.GET.get('batch') or request.POST.get('batch_id')
    if batch_pk:
        batch = get_object_or_404(StockBatch, pk=batch_pk, company=company)

    if request.method == 'POST':
        form = StockCorrectionForm(request.POST)
        if form.is_valid():
            movement              = form.save(commit=False)
            movement.company      = company
            movement.movement_type = 'correction'
            if batch:
                movement.ingredient  = batch.ingredient
                movement.recipe      = batch.recipe
                movement.stock_batch = batch
                # Mettre à jour le lot
                try:
                    batch.consume(abs(movement.quantity))
                except ValueError as e:
                    messages.error(request, str(e))
                    return render(request, 'stock/partials/correction_drawer.html', {
                        'form': form, 'batch': batch, 'form_action': request.path,
                    })
            movement.save()
            messages.success(request, "Correction enregistrée.")
            if request.headers.get('HX-Request'):
                # Rafraîchit la ligne du lot dans le tableau
                batches = StockBatch.objects.filter(
                    company=company, is_depleted=False
                ).select_related('ingredient', 'recipe', 'storage_place').order_by(
                    'ingredient__name', 'best_before'
                )
                return render(request, 'stock/partials/batch_table.html', {
                    'batches': batches, 'today': localdate()
                })
            return redirect('stock:batch_list')
    else:
        form = StockCorrectionForm()

    return render(request, 'stock/partials/correction_drawer.html', {
        'form': form, 'batch': batch, 'form_action': request.path,
    })


# ── Inventaires ────────────────────────────────────────────────────────────────

@login_required
@require_role('owner', 'admin', 'production')
def inventory_list(request):
    company     = _get_company(request)
    inventories = Inventory.objects.filter(company=company)
    return render(request, 'stock/inventory_list.html', {
        'company': company, 'inventories': inventories,
    })


@login_required
@require_role('owner', 'admin', 'production')
def inventory_create(request):
    """
    Crée un nouvel inventaire et pré-remplit les lignes
    depuis les StockLevels existants.
    """
    company = _get_company(request)

    # Un seul inventaire en cours à la fois
    if Inventory.objects.filter(company=company, status='draft').exists():
        messages.warning(request, "Un inventaire est déjà en cours.")
        return redirect('stock:inventory_list')

    if request.method == 'POST':
        form = InventoryForm(request.POST)
        if form.is_valid():
            inventory         = form.save(commit=False)
            inventory.company = company
            inventory.save()

            # Pré-remplit les lignes depuis StockLevel
            from apps.catalog.models import Ingredient
            ingredients = Ingredient.objects.filter(
                tenant=request.tenant, is_active=True
            ).order_by('name')

            # Index des stocks existants
            stock_index = {
                l.ingredient_id: l.quantity
                for l in StockLevel.objects.filter(
                    company=company, ingredient__isnull=False
                )
            }

            lines = []
            for ingredient in ingredients:
                qty = stock_index.get(ingredient.pk, 0)
                lines.append(InventoryLine(
                    inventory=inventory,
                    ingredient=ingredient,
                    recipe=None,
                    unit=ingredient.use_unit,
                    theoretical_quantity=max(qty, 0),
                    counted_quantity=max(qty, 0),
                ))
            InventoryLine.objects.bulk_create(lines)

            messages.success(request, f"Inventaire créé avec {len(lines)} articles.")
            return redirect('stock:inventory_detail', pk=inventory.pk)
    else:
        form = InventoryForm()

    return render(request, 'stock/inventory_form.html', {
        'company': company, 'form': form,
    })

@login_required
@require_role('owner', 'admin', 'production', 'worker')
def inventory_line_add(request, pk):
    company   = _get_company(request)
    inventory = get_object_or_404(Inventory, pk=pk, company=company, status='draft')

    from apps.catalog.models import Ingredient, Recipe
    if request.method == 'POST':
        ingredient_pk = request.POST.get('ingredient')
        recipe_pk     = request.POST.get('recipe')
        counted_qty   = request.POST.get('counted_quantity', 0)
        unit          = request.POST.get('unit', '')

        ingredient = recipe = None
        if ingredient_pk:
            ingredient = get_object_or_404(Ingredient, pk=ingredient_pk)
            unit = unit or ingredient.use_unit
        elif recipe_pk:
            recipe = get_object_or_404(Recipe, pk=recipe_pk)
            unit = unit or recipe.output_unit

        # Évite les doublons
        exists = InventoryLine.objects.filter(
            inventory=inventory,
            ingredient=ingredient,
            recipe=recipe,
        ).exists()

        if not exists:
            line = InventoryLine.objects.create(
                inventory=inventory,
                ingredient=ingredient,
                recipe=recipe,
                unit=unit,
                theoretical_quantity=0,
                counted_quantity=counted_qty,
            )

        lines = inventory.lines.select_related('ingredient', 'recipe').order_by(
            'ingredient__name', 'recipe__name'
        )
        return render(request, 'stock/partials/inventory_lines_tbody.html', {
            'lines': lines, 'inventory': inventory,
        })

    # GET — drawer de sélection
    ingredients = Ingredient.objects.filter(
        tenant=request.tenant, is_active=True
    ).order_by('name')
    recipes = Recipe.objects.filter(
        tenant=request.tenant, is_active=True
    ).order_by('name')
    return render(request, 'stock/partials/inventory_line_add_drawer.html', {
        'inventory': inventory,
        'ingredients': ingredients,
        'recipes': recipes,
        'form_action': request.path,
    })


@login_required
@require_role('owner', 'admin', 'production', 'worker')
def inventory_detail(request, pk):
    company   = _get_company(request)
    inventory = get_object_or_404(Inventory, pk=pk, company=company)
    lines     = inventory.lines.select_related('ingredient', 'recipe').order_by(
        'ingredient__name', 'recipe__name'
    )
    return render(request, 'stock/inventory_detail.html', {
        'company': company, 'inventory': inventory, 'lines': lines,
    })


@login_required
@require_role('owner', 'admin', 'production', 'worker')
def inventory_line_edit(request, pk, lpk):
    """Saisie de la quantité comptée — HTMX, optimisé mobile."""
    company   = _get_company(request)
    inventory = get_object_or_404(Inventory, pk=pk, company=company, status='draft')
    line      = get_object_or_404(InventoryLine, pk=lpk, inventory=inventory)

    if request.method == 'POST':
        form = InventoryLineForm(request.POST, instance=line)
        if form.is_valid():
            form.save()
            return render(request, 'stock/partials/inventory_line_row.html', {
                'line': line, 'inventory': inventory,
            })
    else:
        form = InventoryLineForm(instance=line)

    return render(request, 'stock/partials/inventory_line_edit.html', {
        'form': form, 'line': line, 'inventory': inventory,
        'form_action': request.path,
    })


@login_required
@require_role('owner', 'admin')
def inventory_validate(request, pk):
    company   = _get_company(request)
    inventory = get_object_or_404(Inventory, pk=pk, company=company, status='draft')

    if request.method == 'POST':
        inventory.validate()
        messages.success(request, "Inventaire validé. Les stocks ont été corrigés.")
        return redirect('stock:inventory_list')

    # Résumé des écarts avant validation
    lines_with_delta = [l for l in inventory.lines.select_related('ingredient', 'recipe') if l.delta != 0]
    return render(request, 'stock/inventory_confirm_validate.html', {
        'company': company, 'inventory': inventory,
        'lines_with_delta': lines_with_delta,
    })


# ── Transferts internes ────────────────────────────────────────────────────────

@login_required
@require_role('owner', 'admin', 'production')
def transfer_list(request):
    company   = _get_company(request)
    transfers = InternalTransfer.objects.filter(
        Q(from_company=company) | Q(to_company=company)
    ).select_related('from_company', 'to_company').order_by('-transfer_date')

    return render(request, 'stock/transfer_list.html', {
        'company': company, 'transfers': transfers,
    })


@login_required
@require_role('owner', 'admin', 'production')
def transfer_create(request):
    company = _get_company(request)

    # Sites du même tenant (sauf le site actuel)
    from apps.company.models import Company
    company_qs = Company.objects.filter(
        tenant=request.tenant, is_active=True
    ).exclude(pk=company.pk)

    if request.method == 'POST':
        form = InternalTransferForm(request.POST, from_company=company, company_qs=company_qs)
        if form.is_valid():
            transfer              = form.save(commit=False)
            transfer.from_company = company
            transfer.save()
            messages.success(request, "Transfert créé.")
            return redirect('stock:transfer_detail', pk=transfer.pk)
    else:
        form = InternalTransferForm(from_company=company, company_qs=company_qs)

    return render(request, 'stock/transfer_form.html', {
        'company': company, 'form': form,
    })


@login_required
@require_role('owner', 'admin', 'production', 'worker')
def transfer_detail(request, pk):
    company  = _get_company(request)
    transfer = get_object_or_404(
        InternalTransfer,
        pk=pk,
    )
    # Vérifier que le user a accès à l'un des deux sites
    if transfer.from_company != company and transfer.to_company != company:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    lines = transfer.lines.select_related('ingredient', 'recipe')
    return render(request, 'stock/transfer_detail.html', {
        'company': company, 'transfer': transfer, 'lines': lines,
    })


@login_required
@require_role('owner', 'admin', 'production')
def transfer_line_add(request, pk):
    company  = _get_company(request)
    transfer = get_object_or_404(InternalTransfer, pk=pk, from_company=company, status='draft')

    from apps.catalog.models import Ingredient, Recipe
    ingredient_qs = Ingredient.objects.filter(tenant=request.tenant, is_active=True)
    recipe_qs     = Recipe.objects.filter(tenant=request.tenant, is_active=True)
    print("DEBUG tenant:", request.tenant)
    print("DEBUG ingredients count:", ingredient_qs.count())

    if request.method == 'POST':
        form = InternalTransferLineForm(
            request.POST,
            ingredient_qs=ingredient_qs,
            recipe_qs=recipe_qs,
        )
        if form.is_valid():
            cd   = form.cleaned_data
            line = InternalTransferLine(
                transfer=transfer,
                quantity=cd['quantity'],
                unit=cd['unit'],
                best_before=cd.get('best_before'),
                tracability_number=cd.get('tracability_number', ''),
            )
            if cd['article_type'] == 'ingredient':
                line.ingredient = cd['ingredient']
                line.date_type  = StockBatch.compute_date_type(
                    cd['ingredient'].target_keeping_temp_max and 3 or 0
                )
            else:
                line.recipe    = cd['recipe']
                line.date_type = StockBatch.compute_date_type(cd['recipe'].shelf_life_days)
            line.save()

            lines = transfer.lines.select_related('ingredient', 'recipe')
            return render(request, 'stock/partials/transfer_lines.html', {
                'transfer': transfer, 'lines': lines,
            })
    else:
        form = InternalTransferLineForm(ingredient_qs=ingredient_qs, recipe_qs=recipe_qs)
    print("DEBUG form ingredient queryset count:", form.fields['ingredient'].queryset.count())
    return render(request, 'stock/partials/transfer_line_drawer.html', {
        'form': form, 'transfer': transfer, 'form_action': request.path,
    })


@login_required
@require_role('owner', 'admin', 'production')
def transfer_line_delete(request, pk, lpk):
    company  = _get_company(request)
    transfer = get_object_or_404(InternalTransfer, pk=pk, from_company=company, status='draft')
    line     = get_object_or_404(InternalTransferLine, pk=lpk, transfer=transfer)
    line.delete()
    lines = transfer.lines.select_related('ingredient', 'recipe')
    return render(request, 'stock/partials/transfer_lines.html', {
        'transfer': transfer, 'lines': lines,
    })


@login_required
@require_role('owner', 'admin', 'production')
def transfer_send(request, pk):
    company  = _get_company(request)
    transfer = get_object_or_404(InternalTransfer, pk=pk, from_company=company, status='draft')
    if request.method == 'POST':
        if not transfer.lines.exists():
            messages.error(request, "Ajoutez au moins une ligne avant d'envoyer.")
            return redirect('stock:transfer_detail', pk=pk)
        transfer.confirm_sent()
        messages.success(request, "Transfert envoyé. Le stock expéditeur a été débité.")
        return redirect('stock:transfer_detail', pk=pk)
    return render(request, 'stock/transfer_confirm_send.html', {
        'company': company, 'transfer': transfer,
    })


@login_required
@require_role('owner', 'admin', 'production')
def transfer_receive(request, pk):
    company  = _get_company(request)
    transfer = get_object_or_404(InternalTransfer, pk=pk, to_company=company, status='sent')
    if request.method == 'POST':
        transfer.confirm_received()
        messages.success(request, "Transfert réceptionné. Le stock a été crédité.")
        return redirect('stock:transfer_detail', pk=pk)
    return render(request, 'stock/transfer_confirm_receive.html', {
        'company': company, 'transfer': transfer,
    })

@login_required
def ingredient_search_htmx(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return render(request, "stock/partials/ingredient_dropdown.html", {"results": []})
    from apps.catalog.models import Ingredient
    results = Ingredient.objects.filter(
        tenant=request.tenant,
        is_active=True,
    ).filter(
        Q(name__icontains=q)
    ).order_by("name")[:15]
    return render(request, "stock/partials/ingredient_dropdown.html", {"results": results})