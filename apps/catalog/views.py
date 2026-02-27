from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from apps.company.mixins import get_current_company

from .models import Ingredient, IngredientCategory
from .forms import IngredientForm



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
        if form.is_valid():
            ingredient = form.save(commit=False)
            ingredient.tenant = request.tenant
            ingredient.save()

            # Vérifie si un résultat OCR est disponible
            from django.core.cache import cache
            ocr_result = cache.get(f"ocr_result_{ingredient.pk}")
            if ocr_result and ocr_result.get("fields_filled"):
                n = len(ocr_result["fields_filled"])
                engine = ocr_result.get("engine", "")
                messages.info(request,
                              f"OCR ({engine}) : {n} champ(s) rempli(s) automatiquement depuis l'étiquette.")

            form.save_m2m()
            messages.success(request, f"Ingrédient « {ingredient.name} » créé.")
            return redirect("catalog:ingredient_list")
    else:
        form = IngredientForm()

    return render(request, "catalog/ingredient_form.html", {
        "form": form, "action": "Créer un ingrédient"
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
    if request.method == "POST":
        form = IngredientForm(request.POST, request.FILES, instance=ingredient)
        if form.is_valid():
            form.save()

            # Vérifie si un résultat OCR est disponible
            from django.core.cache import cache
            ocr_result = cache.get(f"ocr_result_{ingredient.pk}")
            if ocr_result and ocr_result.get("fields_filled"):
                n = len(ocr_result["fields_filled"])
                engine = ocr_result.get("engine", "")
                messages.info(request,
                              f"OCR ({engine}) : {n} champ(s) rempli(s) automatiquement depuis l'étiquette.")

            messages.success(request, f"Ingrédient « {ingredient.name} » mis à jour.")
            return redirect("catalog:ingredient_list")
        else:
            print("ERREURS FORM:", form.errors)
    else:
        form = IngredientForm(instance=ingredient)

    return render(request, "catalog/ingredient_form.html", {
        "form": form,
        "ingredient": ingredient,
        "action": "Modifier l'ingrédient"
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