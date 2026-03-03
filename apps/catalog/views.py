from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.utils import timezone

from apps.company.mixins import get_current_company
from .models import Ingredient, IngredientCategory, Recipe, RecipeLine, RecipeCategory
from .forms import IngredientForm, RecipeForm, RecipeLineForm
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
            form.save()

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
    lines = recipe.lines.select_related(
        "ingredient", "sub_recipe"
    ).order_by("order")
    line_form = RecipeLineForm()
    return render(request, "catalog/recipe_detail.html", {
        "recipe": recipe,
        "lines": lines,
        "line_form": line_form,
    })


@login_required
def recipe_edit(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    if request.method == "POST":
        form = RecipeForm(request.POST, request.FILES, instance=recipe)
        if form.is_valid():
            form.save()
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
def recipe_line_delete_htmx(request, line_pk):
    """HTMX — supprime une ligne et retourne le tableau mis à jour."""
    line   = get_object_or_404(RecipeLine, pk=line_pk)
    recipe = line.recipe
    if request.method == "POST":
        line.delete()

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