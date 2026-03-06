"""
Formulaires de l'app stock.
"""
from django import forms
from django.utils.timezone import localdate

from .models import (
    StockBatch, StockMovement, Inventory, InventoryLine,
    InternalTransfer, InternalTransferLine,
)
from apps.catalog.models import Ingredient, Recipe
from apps.company.models import StoragePlace


class StockCorrectionForm(forms.ModelForm):
    """
    Formulaire de correction manuelle de stock.
    Utilisé pour les pertes, casses, dons...
    """
    class Meta:
        model  = StockMovement
        fields = ['quantity', 'unit', 'correction_reason', 'notes', 'moved_at']
        widgets = {
            'quantity':          forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'unit':              forms.Select(attrs={'class': 'form-select'}),
            'correction_reason': forms.Select(attrs={'class': 'form-select'}),
            'notes':             forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'moved_at':          forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['correction_reason'].required = True
        self.fields['moved_at'].initial = localdate()


class StockBatchEditForm(forms.ModelForm):
    """
    Édition manuelle d'un lot (DLC, lieu de stockage, notes).
    """
    class Meta:
        model  = StockBatch
        fields = ['best_before', 'date_type', 'storage_place', 'tracability_number']
        widgets = {
            'best_before':        forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_type':          forms.Select(attrs={'class': 'form-select'}),
            'storage_place':      forms.Select(attrs={'class': 'form-select'}),
            'tracability_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['storage_place'].queryset = StoragePlace.objects.filter(
                company=company, is_active=True
            )


class InventoryForm(forms.ModelForm):
    class Meta:
        model  = Inventory
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                           'placeholder': 'Observations optionnelles...'}),
        }


class InventoryLineForm(forms.ModelForm):
    class Meta:
        model  = InventoryLine
        fields = ['counted_quantity', 'notes']
        widgets = {
            'counted_quantity': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg text-center',
                'step': '0.001',
                'inputmode': 'decimal',   # clavier numérique sur mobile
            }),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Notes...'}),
        }


class InternalTransferForm(forms.ModelForm):
    class Meta:
        model  = InternalTransfer
        fields = ['to_company', 'transfer_date', 'notes']
        widgets = {
            'to_company':     forms.Select(attrs={'class': 'form-select'}),
            'transfer_date':  forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes':          forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, from_company=None, company_qs=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company_qs is not None:
            self.fields['to_company'].queryset = company_qs
        self.fields['transfer_date'].initial = localdate()


class InternalTransferLineForm(forms.Form):
    """
    Formulaire dynamique pour ajouter une ligne à un transfert.
    Pas un ModelForm car on doit gérer ingredient XOR recipe.
    """
    ARTICLE_TYPE_CHOICES = [
        ("ingredient", "Ingrédient"),
        ("recipe",     "Recette / produit fini"),
    ]

    article_type = forms.ChoiceField(
        choices=ARTICLE_TYPE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial="ingredient",
    )
    ingredient = forms.ModelChoiceField(
        queryset=Ingredient.objects.none(),
        required=False,
        empty_label="— Sélectionner un ingrédient —",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    recipe = forms.ModelChoiceField(
        queryset=Recipe.objects.none(),
        required=False,
        empty_label="— Sélectionner une recette —",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    quantity    = forms.DecimalField(
        max_digits=10, decimal_places=3,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
    )
    unit        = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    best_before = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    tracability_number = forms.CharField(
        max_length=60, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, ingredient_qs=None, recipe_qs=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ingredient_qs is not None:
            self.fields['ingredient'].queryset = ingredient_qs
        if recipe_qs is not None:
            self.fields['recipe'].queryset = recipe_qs

    def clean(self):
        cleaned = super().clean()
        atype = cleaned.get('article_type')
        if atype == 'ingredient' and not cleaned.get('ingredient'):
            self.add_error('ingredient', 'Sélectionnez un ingrédient.')
        elif atype == 'recipe' and not cleaned.get('recipe'):
            self.add_error('recipe', 'Sélectionnez une recette.')
        return cleaned