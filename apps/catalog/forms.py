from django import forms
from apps.utilities.models import Allergen
from apps.pricing.models import PriceRecord
from apps.pricing.forms import PriceRecordForm

from .models import Ingredient, IngredientCategory, Recipe, RecipeLine, RecipeCategory, RecipeStep



class IngredientForm(forms.ModelForm):
    class Meta:
        model = Ingredient
        fields = [
            # Infos générales
            "name", "category",
            "is_organic", "is_vegan", "is_veggie", "is_active",
            "label_photo",
            # Conditionnement
            "purchase_unit", "use_unit",
            "net_weight_kg", "net_volume_l", "density_kg_per_l",
            "pieces_per_package", "packages_per_purchase_unit",
            "yield_rate",
            # Températures
            "target_cooking_temp",
            "target_keeping_temp_min", "target_keeping_temp_max",
            # Allergènes & composition
            "allergens", "composition",
            # Nutrition
            "ciqual_ref",
            "energy_kj", "energy_kcal",
            "fat", "saturates",
            "carbohydrates", "sugars",
            "protein", "salt", "fiber",
        ]
        widgets = {
            # Infos
            "name":     forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            # Conditionnement
            "purchase_unit":              forms.Select(attrs={"class": "form-select"}),
            "use_unit":                   forms.Select(attrs={"class": "form-select"}),
            "net_weight_kg":              forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "net_volume_l":               forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "density_kg_per_l":           forms.NumberInput(attrs={"class": "form-control", "step": "0.001", "placeholder": "ex: 0.800"}),
            "pieces_per_package":         forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "packages_per_purchase_unit": forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "yield_rate":                 forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0", "max": "100", "placeholder": "ex: 85"}),
            # Températures
            "target_cooking_temp":     forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
            "target_keeping_temp_min": forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
            "target_keeping_temp_max": forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
            # Allergènes
            "allergens":   forms.CheckboxSelectMultiple(),
            "composition": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            # Nutrition
            "ciqual_ref":    forms.Select(attrs={"class": "form-select"}),
            "energy_kj":     forms.NumberInput(attrs={"class": "form-control", "step": "0.1", "placeholder": "kJ"}),
            "energy_kcal":   forms.NumberInput(attrs={"class": "form-control", "step": "0.1", "placeholder": "kcal"}),
            "fat":           forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "g"}),
            "saturates":     forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "g"}),
            "carbohydrates": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "g"}),
            "sugars":        forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "g"}),
            "protein":       forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "g"}),
            "salt":          forms.NumberInput(attrs={"class": "form-control", "step": "0.001", "placeholder": "g"}),
            "fiber":         forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "g"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Convertit yield_rate stocké (0-1) en % pour affichage (0-100)
        if self.instance and self.instance.pk:
            self.initial['yield_rate'] = round(float(self.instance.yield_rate) * 100, 1)
        self.fields['yield_rate'].help_text = "Ex: 85 pour 85% de matière utilisable après parage"
        self.fields['density_kg_per_l'].required = False
        self.fields['ciqual_ref'].required = False
        # Libellés courts pour la nutrition
        self.fields['energy_kj'].label    = "Énergie (kJ)"
        self.fields['energy_kcal'].label  = "Énergie (kcal)"
        self.fields['fat'].label          = "Lipides (g)"
        self.fields['saturates'].label    = "dont saturés (g)"
        self.fields['carbohydrates'].label= "Glucides (g)"
        self.fields['sugars'].label       = "dont sucres (g)"
        self.fields['protein'].label      = "Protéines (g)"
        self.fields['salt'].label         = "Sel (g)"
        self.fields['fiber'].label        = "Fibres (g)"

    def clean_yield_rate(self):
        value = self.cleaned_data['yield_rate']
        if value > 1:
            value = value / 100
        return value

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = Ingredient.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                f"Un ingrédient nommé « {name} » existe déjà."
            )
        return name



class RecipeForm(forms.ModelForm):
    class Meta:
        model = Recipe
        fields = [
            "name", "category", "recipe_type",
            "output_quantity", "output_unit", "output_weight_kg",
            "yield_rate",
            "shelf_life_days", "shelf_life_after_opening_days",
            "is_sellable", "is_active",
            "notes", "photo",
        ]
        widgets = {
            # ... widgets existants ...
            "yield_rate": forms.NumberInput(attrs={
                "class": "form-control", "step": "1",
                "min": "0", "max": "100", "placeholder": "ex: 90"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photo'].required = False
        self.fields['yield_rate'].required = False
        if self.instance and self.instance.pk:
            self.initial['yield_rate'] = round(float(self.instance.yield_rate) * 100, 1)
        self.fields['yield_rate'].help_text = "Ex: 90 pour 90% de matière utilisable"

    yield_rate = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=100,
        decimal_places=1,
        widget=forms.NumberInput(attrs={
            "class": "form-control", "step": "1",
            "min": "0", "max": "100", "placeholder": "ex: 90"
        }),
        help_text="Ex: 90 pour 90% de matière utilisable"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photo'].required = False
        if self.instance and self.instance.pk:
            self.initial['yield_rate'] = round(float(self.instance.yield_rate) * 100, 1)

    def clean_yield_rate(self):
        value = self.cleaned_data.get('yield_rate')
        if value is None:
            return 1
        if value > 1:
            value = value / 100
        return value


class RecipeLineForm(forms.ModelForm):
    # Champ unifié pour autocomplete — pas dans le modèle
    source_label = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Rechercher un ingrédient ou une sous-recette...",
            "autocomplete": "off",
        })
    )

    class Meta:
        model = RecipeLine
        fields = ["quantity", "unit", "notes"]
        widgets = {
            "quantity": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.001",
                "placeholder": "Quantité"
            }),
            "unit": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Notes (optionnel)"
            }),
        }


class RecipeStepForm(forms.ModelForm):
    class Meta:
        model = RecipeStep
        fields = ["title", "description", "duration_minutes", "temperature_c", "photo"]
        widgets = {
            "title":            forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Faire fondre le chocolat"}),
            "description":      forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "duration_minutes": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "temperature_c":    forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
        }