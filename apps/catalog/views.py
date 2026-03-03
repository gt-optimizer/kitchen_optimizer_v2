from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
import weasyprint


from apps.company.mixins import get_current_company
from apps.ciqual.models import CiqualIngredient, TenantCiqualMapping
from .models import Ingredient, IngredientCategory, Recipe, RecipeLine, RecipeCategory, RecipeStep
from .forms import IngredientForm, RecipeForm, RecipeLineForm, RecipeStepForm
from apps.pricing.forms import PriceRecordForm
from apps.pricing.models import PriceRecord


@login_required
def ingredient_list(request):
    company = get_current_company(request)
    qs = Ingredient.objects.select_related("category").prefetch_related("allergens")

    # Recherche
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(category__name__icontains=q))

    # Filtres
    category_id = request.GET.get("category")
    if category_id:
        qs = qs.filter(category_id=category_id)

    is_organic = request.GET.get("bio")
    if is_organic:
        qs = qs.filter(is_organic=True)

    categories = IngredientCategory.objects.all()

    # HTMX : retourne juste le tableau
    if request.headers.get("HX-Request"):
        return render(request, "catalog/partials/ingredient_table.html", {
            "ingredients": qs, "q": q
        })

    return render(request, "catalog/ingredient_list.html", {
        "ingredients": qs,
        "categories": categories,
        "q": q,
        "category_id": category_id,
    })


@login_required
def ingredient_create(request):
    if request.method == "POST":
        form = IngredientForm(request.POST, request.FILES)
        price_form = PriceRecordForm(request.POST)
        if form.is_valid():
            ingredient = form.save(commit=False)
            ingredient.tenant = request.tenant
            ingredient.save()
            form.save_m2m()

            # Sauvegarde du prix si renseigné
            if price_form.is_valid() and price_form.cleaned_data.get("price_ht"):
                record = price_form.save(commit=False)
                record.tenant = request.tenant
                record.ingredient = ingredient
                record.channel = "purchase"
                record.source = "manual"
                record.save()

            # OCR
            from django.core.cache import cache
            ocr_result = cache.get(f"ocr_result_{ingredient.pk}")
            if ocr_result and ocr_result.get("fields_filled"):
                n = len(ocr_result["fields_filled"])
                engine = ocr_result.get("engine", "")
                messages.info(request, f"OCR ({engine}) : {n} champ(s) rempli(s) automatiquement.")

            messages.success(request, f"Ingrédient « {ingredient.name} » créé.")
            return redirect("catalog:ingredient_detail", pk=ingredient.pk)
    else:
        form = IngredientForm()
        price_form = PriceRecordForm(initial={"valid_from": timezone.localdate()})

    return render(request, "catalog/ingredient_form.html", {
        "form": form,
        "price_form": price_form,
        "has_price": False,
        "current_price": None,
        "action": "Créer un ingrédient",
    })


@login_required
def ingredient_detail(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)

    # Valeurs nutritionnelles formatées pour le template
    nutri_values = [
        ("Énergie", ingredient.energy_kcal, "kcal"),
        ("Lipides", ingredient.fat, "g"),
        ("dont sat.", ingredient.saturates, "g"),
        ("Glucides", ingredient.carbohydrates, "g"),
        ("dont sucres", ingredient.sugars, "g"),
        ("Protéines", ingredient.protein, "g"),
        ("Sel", ingredient.salt, "g"),
        ("Fibres", ingredient.fiber, "g"),
    ]
    print("label_photo:", ingredient.label_photo)

    return render(request, "catalog/ingredient_detail.html", {
        "ingredient": ingredient,
        "nutri_values": nutri_values,
    })



@login_required
def ingredient_edit(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)

    # Prix courant
    today = timezone.localdate()
    current_record = (
        PriceRecord.objects
        .filter(ingredient=ingredient, channel="purchase", valid_from__lte=today)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
        .order_by("-valid_from")
        .first()
    )
    has_price = current_record is not None
    current_price = current_record.price_ht if current_record else None

    if request.method == "POST":
        form = IngredientForm(request.POST, request.FILES, instance=ingredient)
        price_form = PriceRecordForm(request.POST)
        if form.is_valid():
            ing = form.save(commit=False)

            nutri_fields = [
                "energy_kj", "energy_kcal", "fat", "saturates",
                "carbohydrates", "sugars", "protein", "salt", "fiber"
            ]
            # Recharge depuis la base fraîche (pas depuis `ingredient` qui est stale)
            fresh = Ingredient.objects.get(pk=pk)
            for field in nutri_fields:
                post_val = request.POST.get(field, "").strip()
                if not post_val:
                    setattr(ing, field, getattr(fresh, field))

            if not ing.ciqual_ref_id:
                ing.ciqual_ref = fresh.ciqual_ref

            if not request.FILES.get("label_photo"):
                ing.label_photo = fresh.label_photo

            ing.save()

            # Sauvegarde prix uniquement si pas encore de prix
            if not has_price and price_form.is_valid() and price_form.cleaned_data.get("price_ht"):
                record = price_form.save(commit=False)
                record.tenant = request.tenant
                record.ingredient = ingredient
                record.channel = "purchase"
                record.source = "manual"
                record.save()

            # OCR
            from django.core.cache import cache
            ocr_result = cache.get(f"ocr_result_{ingredient.pk}")
            if ocr_result and ocr_result.get("fields_filled"):
                n = len(ocr_result["fields_filled"])
                engine = ocr_result.get("engine", "")
                messages.info(request, f"OCR ({engine}) : {n} champ(s) rempli(s) automatiquement.")

            messages.success(request, f"Ingrédient « {ingredient.name} » mis à jour.")
            return redirect("catalog:ingredient_detail", pk=ingredient.pk)
        else:
            print("ERREURS FORM:", form.errors)
    else:
        form = IngredientForm(instance=ingredient)
        price_form = PriceRecordForm(initial={"valid_from": timezone.localdate()})

    return render(request, "catalog/ingredient_form.html", {
        "form": form,
        "price_form": price_form,
        "has_price": has_price,
        "current_price": current_price,
        "ingredient": ingredient,
        "action": "Modifier l'ingrédient",
    })


@login_required
def ingredient_delete(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    if request.method == "POST":
        name = ingredient.name
        ingredient.delete()
        messages.success(request, f"Ingrédient « {name} » supprimé.")
        return redirect("catalog:ingredient_list")

    return render(request, "catalog/ingredient_confirm_delete.html", {
        "ingredient": ingredient
    })


@login_required
def ingredient_search_htmx(request):
    """Recherche HTMX — retourne juste les lignes du tableau."""
    q = request.GET.get("q", "").strip()
    qs = Ingredient.objects.select_related("category")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(category__name__icontains=q))
    return render(request, "catalog/partials/ingredient_table.html", {
        "ingredients": qs, "q": q
    })

from apps.ciqual.models import CiqualIngredient, TenantCiqualMapping


@login_required
def ciqual_search_htmx(request):
    """Autocomplete CIQUAL — retourne une liste de suggestions."""
    q = request.GET.get("ciqual_q", request.GET.get("q", "")).strip()
    print("ciqual q=", repr(q), "ciqual_q=", repr(request.GET.get("ciqual_q", "")))

    if len(q) < 2:
        return render(request, "catalog/partials/ciqual_dropdown.html", {"results": []})

    # Mappings tenant en premier (apprentissage)
    mapped_ids = (
        TenantCiqualMapping.objects
        .filter(
            tenant=request.tenant,
            ingredient_name_lower__icontains=q.lower()
        )
        .order_by("-score")
        .values_list("ciqual_ingredient_id", flat=True)[:5]
    )

    # Recherche générale
    qs = CiqualIngredient.objects.filter(
        Q(name_fr__icontains=q) | Q(name_en__icontains=q)
    ).order_by("name_fr")[:20]

    # Priorise les mappings tenant
    mapped = list(CiqualIngredient.objects.filter(pk__in=mapped_ids))
    others = [c for c in qs if c.pk not in mapped_ids]
    results = mapped + others

    return render(request, "catalog/partials/ciqual_dropdown.html", {
        "results": results[:12]
    })


@login_required
def ciqual_apply_htmx(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    ciqual_id  = request.POST.get("ciqual_id")
    overwrite  = request.POST.get("overwrite") == "1"
    ciqual     = get_object_or_404(CiqualIngredient, pk=ciqual_id)
    print("ciqual_id:", ciqual_id, "ciqual:", ciqual)
    nutri = ciqual.to_nutrition_dict()
    filled = []

    for field, value in nutri.items():
        if value is not None:
            current = getattr(ingredient, field, None)
            if not current or overwrite:
                setattr(ingredient, field, value)
                filled.append(field)

    print("filled:", filled)
    ingredient.ciqual_ref = ciqual
    ingredient.save(update_fields=filled + ["ciqual_ref"])
    print("saved OK, energy_kcal now:", ingredient.energy_kcal)

    # Mapping apprentissage
    name_lower = ingredient.name.lower()
    mapping, created = TenantCiqualMapping.objects.get_or_create(
        tenant=request.tenant,
        ingredient_name_lower=name_lower,
        ciqual_ingredient=ciqual,
    )
    if not created:
        mapping.score += 1
        mapping.save(update_fields=["score", "last_used"])

    return render(request, "catalog/partials/ciqual_apply_result.html", {
        "ingredient": ingredient,
        "ciqual": ciqual,
        "filled": filled,
        "overwrite": overwrite,
        "detached": False,
    })

@login_required
def ciqual_preview_htmx(request):
    """Retourne les valeurs nutri CIQUAL en JSON — pour pré-remplir le formulaire de création."""
    ciqual_id = request.GET.get("ciqual_id")
    ciqual = get_object_or_404(CiqualIngredient, pk=ciqual_id)
    return JsonResponse(ciqual.to_nutrition_dict())


@login_required
def ciqual_detach_htmx(request, pk):
    """Délie la référence CIQUAL sans toucher aux valeurs nutri."""
    ingredient = get_object_or_404(Ingredient, pk=pk)
    if request.method == "POST":
        ingredient.ciqual_ref = None
        ingredient.save(update_fields=["ciqual_ref"])
    return render(request, "catalog/partials/ciqual_apply_result.html", {
        "ingredient": ingredient,
        "ciqual": None,
        "filled": [],
        "detached": True,
    })

# ══════════════════════════════════════════════════════════════════════════════
# RECETTES
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def recipe_list(request):
    qs = Recipe.objects.select_related("category").order_by("name")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(category__name__icontains=q) |
            Q(composition_data__icontains=q)
        )

    category_id = request.GET.get("category")
    if category_id:
        qs = qs.filter(category_id=category_id)

    recipe_type = request.GET.get("type")
    if recipe_type:
        qs = qs.filter(recipe_type=recipe_type)

    if request.GET.get("sellable"):
        qs = qs.filter(is_sellable=True)

    if request.GET.get("active"):
        qs = qs.filter(is_active=True)

    categories = RecipeCategory.objects.all()

    if request.headers.get("HX-Request"):
        return render(request, "catalog/partials/recipe_table.html", {
            "recipes": qs, "q": q
        })

    return render(request, "catalog/recipe_list.html", {
        "recipes": qs,
        "categories": categories,
        "q": q,
        "category_id": category_id,
        "recipe_type": recipe_type,
    })


@login_required
def recipe_create(request):
    if request.method == "POST":
        form = RecipeForm(request.POST, request.FILES)
        if form.is_valid():
            recipe = form.save(commit=False)
            recipe.tenant = request.tenant
            recipe.save()
            messages.success(request, f"Recette « {recipe.name} » créée.")
            return redirect("catalog:recipe_detail", pk=recipe.pk)
    else:
        form = RecipeForm()

    return render(request, "catalog/recipe_form.html", {
        "form": form,
        "action": "Créer une recette",
    })


@login_required
def recipe_detail(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    lines = recipe.lines.select_related("ingredient", "sub_recipe").order_by("order")
    steps = recipe.steps.order_by("order")

    today = timezone.localdate()
    current_price = (
        PriceRecord.objects
        .filter(
            recipe=recipe,
            channel__in=("retail", "wholesale"),
            valid_from__lte=today,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
        .select_related("vat_rate")
        .order_by("-valid_from")
        .first()
    )

    return render(request, "catalog/recipe_detail.html", {
        "recipe": recipe,
        "lines": lines,
        "steps": steps,
        "line_form": RecipeLineForm(),
        "step_form": RecipeStepForm(),
        "current_price": current_price,
    })


@login_required
def recipe_edit(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    if request.method == "POST":
        form = RecipeForm(request.POST, request.FILES, instance=recipe)
        print("FORM VALID:", form.is_valid())
        print("FORM ERRORS:", form.errors)
        if form.is_valid():
            recipe = form.save(commit=False)
            # Si pas de nouvelle photo uploadée, garde l'ancienne
            if not request.FILES.get('photo'):
                recipe.photo = Recipe.objects.get(pk=recipe.pk).photo
            recipe.save()
            form.save_m2m()
            messages.success(request, f"Recette « {recipe.name} » mise à jour.")
            return redirect("catalog:recipe_detail", pk=recipe.pk)
    else:
        form = RecipeForm(instance=recipe)

    return render(request, "catalog/recipe_form.html", {
        "form": form,
        "recipe": recipe,
        "action": "Modifier la recette",
    })


@login_required
def recipe_delete(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    if request.method == "POST":
        name = recipe.name
        recipe.delete()
        messages.success(request, f"Recette « {name} » supprimée.")
        return redirect("catalog:recipe_list")
    return render(request, "catalog/recipe_confirm_delete.html", {
        "recipe": recipe
    })


@login_required
def recipe_search_htmx(request):
    q = request.GET.get("q", "").strip()
    qs = Recipe.objects.select_related("category")
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(composition_data__icontains=q)
        )
    return render(request, "catalog/partials/recipe_table.html", {
        "recipes": qs, "q": q
    })


@login_required
def recipe_line_add_htmx(request, pk):
    """
    HTMX — ajoute une ligne à la recette.
    Retourne le tableau des lignes mis à jour + le coût total.
    """
    recipe = get_object_or_404(Recipe, pk=pk)
    if request.method == "POST":
        form = RecipeLineForm(request.POST)
        ingredient_id  = request.POST.get("ingredient_id")
        sub_recipe_id  = request.POST.get("sub_recipe_id")
        print("ingredient_id:", ingredient_id, "sub_recipe_id:", sub_recipe_id)
        print("form valid:", form.is_valid())
        print("form errors:", form.errors)

        if form.is_valid() and (ingredient_id or sub_recipe_id):
            line = form.save(commit=False)
            line.recipe = recipe
            line.order  = recipe.lines.count() + 1

            if ingredient_id:
                line.ingredient = get_object_or_404(Ingredient, pk=ingredient_id)
            elif sub_recipe_id:
                line.sub_recipe = get_object_or_404(Recipe, pk=sub_recipe_id)

            line.save()

    lines = recipe.lines.select_related(
        "ingredient", "sub_recipe"
    ).order_by("order")
    recipe.refresh_from_db()

    return render(request, "catalog/partials/recipe_lines.html", {
        "recipe": recipe,
        "lines": lines,
        "line_form": RecipeLineForm(),
    })


@login_required
def recipe_line_edit_htmx(request, line_pk):
    line = get_object_or_404(RecipeLine, pk=line_pk)
    recipe = line.recipe

    if request.method == "POST":
        form = RecipeLineForm(request.POST, instance=line)
        if form.is_valid():
            form.save()
            recipe.refresh_from_db()
            lines = recipe.lines.select_related("ingredient", "sub_recipe").order_by("order")

            drawer_html = render_to_string(
                "catalog/partials/recipe_line_drawer.html",
                {"line": line, "recipe": recipe, "form": RecipeLineForm(instance=line), "saved": True},
                request=request,
            )
            lines_html = render_to_string(
                "catalog/partials/recipe_lines.html",
                {"recipe": recipe, "lines": lines, "line_form": RecipeLineForm()},
                request=request,
            )
            # OOB swap — met à jour le tableau en même temps que le drawer
            oob_div = f'<div id="recipe-lines-container" hx-swap-oob="true">{lines_html}</div>'
            from django.http import HttpResponse
            return HttpResponse(drawer_html + oob_div)
    else:
        form = RecipeLineForm(instance=line)

    return render(request, "catalog/partials/recipe_line_drawer.html", {
        "line": line,
        "recipe": recipe,
        "form": form,
        "saved": False,
    })


@login_required
def ingredient_cost_htmx(request):
    """
    HTMX — autocomplete unifié ingrédients + sous-recettes.
    Retourne un dropdown HTML.
    """
    q = request.GET.get("q", "").strip()
    print("q=", q, "exclude_pk=", request.GET.get("exclude_pk"))
    if len(q) < 2:
        return render(request, "catalog/partials/autocomplete_dropdown.html", {
            "results": []
        })

    ingredients = Ingredient.objects.filter(
        name__icontains=q, is_active=True
    )[:8]
    print("ingredients trouvés:", list(ingredients.values_list("name", flat=True)))


    sub_recipes = Recipe.objects.filter(
        name__icontains=q, is_active=True
    ).exclude(pk=request.GET.get("exclude_pk"))[:8]

    results = []
    for ing in ingredients:
        results.append({
            "id":       ing.pk,
            "label":    ing.name,
            "type":     "ingredient",
            "type_display": "Ingrédient",
            "cost":     float(ing.cost_per_use_unit),
            "unit":     ing.get_use_unit_display(),
        })
    for sr in sub_recipes:
        results.append({
            "id":       sr.pk,
            "label":    sr.name,
            "type":     "sub_recipe",
            "type_display": "Sous-recette",
            "cost":     sr.cost_per_unit,
            "unit":     sr.get_output_unit_display(),
        })

    return render(request, "catalog/partials/autocomplete_dropdown.html", {
        "results": results
    })

@login_required
def recipe_line_delete_htmx(request, line_pk):
    line = get_object_or_404(RecipeLine, pk=line_pk)
    recipe = line.recipe
    if request.method == "POST":
        line.delete()

    lines = recipe.lines.select_related("ingredient", "sub_recipe").order_by("order")
    recipe.refresh_from_db()

    return render(request, "catalog/partials/recipe_lines.html", {
        "recipe": recipe,
        "lines": lines,
        "line_form": RecipeLineForm(),
    })


def _render_steps(request, recipe):
    steps = recipe.steps.order_by("order")
    return render(request, "catalog/partials/recipe_steps.html", {
        "recipe": recipe,
        "steps": steps,
        "step_form": RecipeStepForm(),
    })


@login_required
def recipe_step_add_htmx(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    if request.method == "POST":
        form = RecipeStepForm(request.POST, request.FILES)
        if form.is_valid():
            step = form.save(commit=False)
            step.recipe = recipe
            step.order = recipe.steps.count() + 1
            step.save()
    return _render_steps(request, recipe)


@login_required
def recipe_step_delete_htmx(request, step_pk):
    step = get_object_or_404(RecipeStep, pk=step_pk)
    recipe = step.recipe
    if request.method == "POST":
        order = step.order
        step.delete()
        # Réordonne les étapes suivantes
        for s in recipe.steps.filter(order__gt=order).order_by("order"):
            s.order -= 1
            s.save(update_fields=["order"])
    return _render_steps(request, recipe)


@login_required
def recipe_step_move_htmx(request, step_pk):
    step = get_object_or_404(RecipeStep, pk=step_pk)
    recipe = step.recipe
    direction = request.POST.get("direction")  # "up" ou "down"

    if direction == "up" and step.order > 1:
        other = recipe.steps.filter(order=step.order - 1).first()
        if other:
            other.order, step.order = step.order, other.order
            other.save(update_fields=["order"])
            step.save(update_fields=["order"])

    elif direction == "down":
        other = recipe.steps.filter(order=step.order + 1).first()
        if other:
            other.order, step.order = step.order, other.order
            other.save(update_fields=["order"])
            step.save(update_fields=["order"])

    return _render_steps(request, recipe)


@login_required
def recipe_step_edit_htmx(request, step_pk):
    step = get_object_or_404(RecipeStep, pk=step_pk)
    recipe = step.recipe

    if request.method == "POST":
        form = RecipeStepForm(request.POST, request.FILES, instance=step)
        if form.is_valid():
            form.save()
            steps_html = render_to_string(
                "catalog/partials/recipe_steps.html",
                {"recipe": recipe, "steps": recipe.steps.order_by("order"), "step_form": RecipeStepForm()},
                request=request,
            )
            drawer_html = render_to_string(
                "catalog/partials/recipe_step_drawer.html",
                {"step": step, "recipe": recipe, "form": RecipeStepForm(instance=step), "saved": True},
                request=request,
            )
            oob = f'<div id="recipe-steps-container" hx-swap-oob="true">{steps_html}</div>'
            from django.http import HttpResponse
            return HttpResponse(drawer_html + oob)
    else:
        form = RecipeStepForm(instance=step)

    return render(request, "catalog/partials/recipe_step_drawer.html", {
        "step": step,
        "recipe": recipe,
        "form": form,
        "saved": False,
    })


from django.http import HttpResponse
from django.template.loader import render_to_string
import weasyprint


@login_required
def recipe_pdf(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    lines = recipe.lines.select_related("ingredient", "sub_recipe").order_by("order")
    steps = recipe.steps.order_by("order")

    html = render_to_string("catalog/recipe_pdf.html", {
        "recipe": recipe,
        "lines": lines,
        "steps": steps,
        "company": request.tenant,
        "date": timezone.localdate(),
        "request": request,
    })

    pdf = weasyprint.HTML(
        string=html,
        base_url=request.build_absolute_uri("/")
    ).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="fiche_{recipe.name.replace(" ", "_")}.pdf"'
    )
    return response


@login_required
def recipe_duplicate(request, pk):
    original = get_object_or_404(Recipe, pk=pk)

    if request.method == "POST":
        # Duplique la recette
        new_recipe = Recipe.objects.get(pk=pk)
        new_recipe.pk = None
        new_recipe.name = f"{original.name} (copie)"
        new_recipe.cost_total_cached = 0
        new_recipe.composition_data = {}
        new_recipe.save()

        # Duplique les lignes
        for line in original.lines.select_related("ingredient", "sub_recipe").order_by("order"):
            line.pk = None
            line.recipe = new_recipe
            line.save()

        # Duplique les étapes
        for step in original.steps.order_by("order"):
            old_photo = step.photo
            step.pk = None
            step.recipe = new_recipe
            step.photo = old_photo  # garde la même photo (pas de copie physique)
            step.save()

        messages.success(request, f"Recette « {new_recipe.name} » créée — modifiez-la selon vos besoins.")
        return redirect("catalog:recipe_detail", pk=new_recipe.pk)

    return render(request, "catalog/recipe_confirm_duplicate.html", {
        "recipe": original,
    })
