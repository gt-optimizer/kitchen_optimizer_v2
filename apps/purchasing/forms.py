from django import forms
from .models import Supplier, DeliveryDocument


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