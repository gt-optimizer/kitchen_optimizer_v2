from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils import timezone

from apps.catalog.models import Ingredient, Recipe
from .models import PriceRecord
from .forms import PriceRecordForm, RecipePriceRecordForm


@login_required
def ingredient_price_drawer(request, ingredient_pk):
    ingredient = get_object_or_404(Ingredient, pk=ingredient_pk)
    prices = (
        PriceRecord.objects
        .filter(ingredient=ingredient, channel="purchase")
        .select_related("vat_rate")
        .order_by("-valid_from")
    )
    return render(request, "pricing/partials/price_drawer.html", {
        "ingredient": ingredient,
        "prices": prices,
    })


@login_required
def ingredient_price_add(request, ingredient_pk):
    ingredient = get_object_or_404(Ingredient, pk=ingredient_pk)
    if request.method == "POST":
        form = PriceRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.tenant = request.tenant
            record.ingredient = ingredient
            record.channel = "purchase"
            record.save()
            prices = (
                PriceRecord.objects
                .filter(ingredient=ingredient, channel="purchase")
                .order_by("-valid_from")
            )
            return render(request, "pricing/partials/price_drawer.html", {
                "ingredient": ingredient,
                "prices": prices,
            })
    else:
        form = PriceRecordForm(initial={"valid_from": timezone.localdate()})

    return render(request, "pricing/partials/price_form.html", {
        "form": form,
        "ingredient": ingredient,
    })


@login_required
def ingredient_price_delete(request, pk):
    record = get_object_or_404(PriceRecord, pk=pk)
    ingredient = record.ingredient
    if request.method == "POST":
        record.delete()
        prices = (
            PriceRecord.objects
            .filter(ingredient=ingredient, channel="purchase")
            .order_by("-valid_from")
        )
        return render(request, "pricing/partials/price_drawer.html", {
            "ingredient": ingredient,
            "prices": prices,
        })


def _render_recipe_price_response(request, recipe):
    """Helper — retourne drawer + OOB swap onglet prix recette."""
    today = timezone.localdate()
    prices = PriceRecord.objects.filter(
        recipe=recipe,
        channel__in=("retail", "wholesale"),
    ).select_related("vat_rate").order_by("-valid_from")

    current = (
        prices.filter(valid_from__lte=today)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
        .first()
    )

    drawer_html = render_to_string(
        "pricing/partials/recipe_price_drawer.html",
        {"recipe": recipe, "prices": prices, "current": current,
         "form": PriceRecordForm(), "request": request},
        request=request,
    )
    tab_html = render_to_string(
        "catalog/partials/recipe_price_tab.html",
        {"recipe": recipe, "prices": prices, "current": current},
        request=request,
    )
    oob = f'<div id="recipe-price-tab-content" hx-swap-oob="true">{tab_html}</div>'
    return HttpResponse(drawer_html + oob)


@login_required
def recipe_price_drawer(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    return _render_recipe_price_response(request, recipe)


@login_required
def recipe_price_add(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    if request.method == "POST":
        form = RecipePriceRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.tenant = request.tenant
            record.recipe = recipe
            record.source = "manual"
            record.save()
            return _render_recipe_price_response(request, recipe)
        # Form invalide — réaffiche le drawer avec erreurs
        drawer_html = render_to_string(
            "pricing/partials/recipe_price_form.html",
            {"recipe": recipe, "form": form},
            request=request,
        )
        return HttpResponse(drawer_html)
    else:
        form = RecipePriceRecordForm()
        return render(request, "pricing/partials/recipe_price_form.html", {
            "recipe": recipe, "form": form,
        })


@login_required
def recipe_price_delete(request, price_pk):
    record = get_object_or_404(PriceRecord, pk=price_pk)
    recipe = record.recipe
    if request.method == "POST":
        record.delete()
    return _render_recipe_price_response(request, recipe)