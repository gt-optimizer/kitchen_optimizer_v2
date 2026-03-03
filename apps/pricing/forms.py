from django import forms
from django.core.exceptions import ValidationError

from .models import PriceRecord


class PriceRecordForm(forms.ModelForm):
    class Meta:
        model = PriceRecord
        fields = ["price_ht", "valid_from", "valid_until", "notes"]
        widgets = {
            "valid_from":  forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "valid_until": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "price_ht":    forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
            "notes":       forms.TextInput(attrs={"class": "form-control"}),
        }


class RecipePriceRecordForm(forms.ModelForm):
    class Meta:
        model = PriceRecord
        fields = ["channel", "price_ttc", "vat_rate", "valid_from", "valid_until", "notes"]
        widgets = {
            "channel":     forms.Select(attrs={"class": "form-select"}),
            "price_ttc":   forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "vat_rate":    forms.Select(attrs={"class": "form-select"}),
            "valid_from":  forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "valid_until": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "notes":       forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Exclut le canal "purchase" — réservé aux ingrédients
        self.fields["channel"].choices = [
            c for c in PriceRecord.CHANNEL_CHOICES
            if c[0] in ("retail", "wholesale")
        ]
        self.fields["vat_rate"].required = True
        self.fields["price_ttc"].required = True