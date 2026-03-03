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


