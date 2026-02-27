from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.contrib import messages
from django.utils import timezone

from apps.catalog.models import Ingredient
from .models import PriceRecord
from .forms import PriceRecordForm


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
