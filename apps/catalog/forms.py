from django import forms
from .models import Ingredient, IngredientCategory
from apps.utilities.models import Allergen


class IngredientForm(forms.ModelForm):
    class Meta:
        model = Ingredient
        fields = [
            "name", "category",
            "purchase_unit", "use_unit",
            "net_weight_kg", "net_volume_l", "pieces_per_package", "packages_per_purchase_unit",
            "composition", "label_photo",
            "yield_rate", "reference_price",
            "is_organic", "is_vegan", "is_veggie",
            "allergens",
            "target_cooking_temp", "target_keeping_temp_min", "target_keeping_temp_max",
        ]
        widgets = {
            "allergens": forms.CheckboxSelectMultiple(),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "purchase_unit": forms.Select(attrs={"class": "form-select"}),
            "packages_per_purchase_unit": forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "use_unit": forms.Select(attrs={"class": "form-select"}),
            "yield_rate": forms.NumberInput(attrs={
                "class": "form-control", "step": "1", "min": "0", "max": "100",
                "placeholder": "ex: 85"
            }),
            "reference_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
            "net_weight_kg": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "net_volume_l": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "pieces_per_package": forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "composition": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "target_cooking_temp": forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
            "target_keeping_temp_min": forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
            "target_keeping_temp_max": forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not args and self.instance and self.instance.pk:
            self.initial['yield_rate'] = round(float(self.instance.yield_rate) * 100, 1)
        self.fields['yield_rate'].help_text = "Ex: 85 pour 85% de matière utilisable après parage"

    def clean_yield_rate(self):
        value = self.cleaned_data['yield_rate']
        # Convertit 85 → 0.85 avant stockage
        if value > 1:
            value = value / 100
        return round(value, 3)