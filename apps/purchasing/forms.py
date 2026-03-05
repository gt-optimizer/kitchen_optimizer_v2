from django import forms
from .models import Supplier, DeliveryDocument, SupplierIngredient, SupplierContact


class SupplierForm(forms.ModelForm):
    class Meta:
        model  = Supplier
        fields = [
            "name", "address", "zipcode", "city",
            "phone", "email", "rcs", "siret", "vat_number", "is_active"
        ]
        widgets = {
            "name":       forms.TextInput(attrs={"class": "form-control"}),
            "address":    forms.TextInput(attrs={"class": "form-control"}),
            "zipcode":    forms.TextInput(attrs={"class": "form-control"}),
            "city":       forms.TextInput(attrs={"class": "form-control"}),
            "phone":      forms.TextInput(attrs={"class": "form-control"}),
            "email":      forms.EmailInput(attrs={"class": "form-control"}),
            "rcs":        forms.TextInput(attrs={"class": "form-control"}),
            "siret":      forms.TextInput(attrs={"class": "form-control"}),
            "vat_number": forms.TextInput(attrs={"class": "form-control"}),
        }

class SupplierContactForm(forms.ModelForm):
    class Meta:
        model  = SupplierContact
        fields = ["first_name", "last_name", "job_title", "phone", "mobile", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name":  forms.TextInput(attrs={"class": "form-control"}),
            "job_title":  forms.TextInput(attrs={"class": "form-control"}),
            "phone":      forms.TextInput(attrs={"class": "form-control"}),
            "mobile":     forms.TextInput(attrs={"class": "form-control"}),
            "email":      forms.EmailInput(attrs={"class": "form-control"}),
        }


class SupplierIngredientForm(forms.ModelForm):
    class Meta:
        model  = SupplierIngredient
        fields = [
            "ingredient", "supplier_item_number", "supplier_item_name",
            "ean13", "negotiated_price", "is_preferred", "is_active"
        ]
        widgets = {
            "ingredient":           forms.Select(attrs={"class": "form-select"}),
            "supplier_item_number": forms.TextInput(attrs={"class": "form-control"}),
            "supplier_item_name":   forms.TextInput(attrs={"class": "form-control"}),
            "ean13":                forms.TextInput(attrs={"class": "form-control"}),
            "negotiated_price":     forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
        }

    def __init__(self, *args, tenant=None, supplier=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            from apps.catalog.models import Ingredient
            self.fields["ingredient"].queryset = Ingredient.objects.filter(
                tenant=tenant, is_active=True
            ).order_by("name")
        # Exclure les ingrédients déjà liés à ce fournisseur (sauf l'instance en cours)
        if supplier and not self.instance.pk:
            already_linked = SupplierIngredient.objects.filter(
                supplier=supplier
            ).values_list("ingredient_id", flat=True)
            self.fields["ingredient"].queryset = self.fields["ingredient"].queryset.exclude(
                pk__in=already_linked
            )


class DeliveryDocumentForm(forms.ModelForm):
    class Meta:
        model  = DeliveryDocument
        fields = ["supplier", "document_type", "document", "reference", "notes"]
        widgets = {
            "supplier":      forms.Select(attrs={"class": "form-select"}),
            "document_type": forms.Select(attrs={"class": "form-select"}),
            "document":      forms.FileInput(attrs={"class": "form-control", "accept": ".pdf,.png,.jpg,.jpeg"}),
            "reference":     forms.TextInput(attrs={"class": "form-control", "placeholder": "N° BL ou facture (optionnel)"}),
            "notes":         forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields["supplier"].queryset = Supplier.objects.filter(
                tenant=tenant, is_active=True
            )
        self.fields["supplier"].required = False
        self.fields["supplier"].empty_label = "— Fournisseur inconnu —"