from django import forms
from .models import CarcassTemplate, CarcassTemplateLine, ButcherySession, ButcheryLine


class CarcassTemplateForm(forms.ModelForm):
    class Meta:
        model  = CarcassTemplate
        fields = ["name", "species", "purchase_unit", "description", "is_active"]
        widgets = {
            "name":          forms.TextInput(attrs={"class": "form-control"}),
            "species":       forms.Select(attrs={"class": "form-select"}),
            "purchase_unit": forms.TextInput(attrs={"class": "form-control",
                             "placeholder": "Ex: demi-carcasse, poulet entier..."}),
            "description":   forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class CarcassTemplateLineForm(forms.ModelForm):
    class Meta:
        model  = CarcassTemplateLine
        fields = [
            "name", "norm_code", "output_type", "linked_ingredient",
            "selling_price_ttc", "vat_rate", "expected_yield_pct",
            "parent", "order", "notes",
        ]
        widgets = {
            "name":               forms.TextInput(attrs={"class": "form-control"}),
            "norm_code":          forms.TextInput(attrs={"class": "form-control"}),
            "output_type":        forms.Select(attrs={"class": "form-select"}),
            "linked_ingredient":  forms.Select(attrs={"class": "form-select"}),
            "selling_price_ttc":  forms.NumberInput(attrs={"class": "form-control",
                                  "step": "0.01"}),
            "vat_rate":           forms.NumberInput(attrs={"class": "form-control",
                                  "step": "0.001"}),
            "expected_yield_pct": forms.NumberInput(attrs={"class": "form-control",
                                  "step": "0.1"}),
            "parent":             forms.Select(attrs={"class": "form-select"}),
            "order":              forms.NumberInput(attrs={"class": "form-control"}),
            "notes":              forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, template=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.catalog.models import Ingredient
        self.fields["linked_ingredient"].queryset = Ingredient.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["linked_ingredient"].required = False
        self.fields["linked_ingredient"].empty_label = "— Aucun —"
        self.fields["norm_code"].required = False

        if template:
            # Filtre les parents possibles (lignes du même gabarit, pas soi-même)
            qs = CarcassTemplateLine.objects.filter(template=template)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields["parent"].queryset = qs
            self.fields["parent"].empty_label = "— Racine (pas de parent) —"
        else:
            self.fields["parent"].queryset = CarcassTemplateLine.objects.none()

        self.fields["parent"].required = False


class ButcherySessionForm(forms.ModelForm):
    class Meta:
        model  = ButcherySession
        fields = [
            "description", "species", "session_date", "template",
            "purchase_weight_kg", "purchase_price_per_kg",
            "sector_tax_total_ht", "processing_cost_ht", "notes",
        ]
        widgets = {
            "description":          forms.TextInput(attrs={"class": "form-control",
                                    "placeholder": "Ex: Demi-bœuf Charolaise n°47 — SCA Le Pré Vert"}),
            "species":              forms.Select(attrs={"class": "form-select"}),
            "session_date":         forms.DateInput(attrs={"class": "form-control",
                                    "type": "date"}),
            "template":             forms.Select(attrs={"class": "form-select"}),
            "purchase_weight_kg":   forms.NumberInput(attrs={"class": "form-control",
                                    "step": "0.001"}),
            "purchase_price_per_kg": forms.NumberInput(attrs={"class": "form-control",
                                    "step": "0.0001"}),
            "sector_tax_total_ht":  forms.NumberInput(attrs={"class": "form-control",
                                    "step": "0.01"}),
            "processing_cost_ht":   forms.NumberInput(attrs={"class": "form-control",
                                    "step": "0.01"}),
            "notes":                forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields["template"].queryset = CarcassTemplate.objects.filter(
                tenant=tenant, is_active=True
            )
        self.fields["template"].required = False
        self.fields["template"].empty_label = "— Sans gabarit —"
        self.fields["sector_tax_total_ht"].required = False
        self.fields["processing_cost_ht"].required = False


class ButcheryLineForm(forms.ModelForm):
    class Meta:
        model  = ButcheryLine
        fields = [
            "name", "output_type", "real_weight_kg",
            "selling_price_ttc", "vat_rate",
            "linked_ingredient", "parent_line", "template_line",
            "byproduct_selling_price", "byproduct_sold",
            "order", "notes",
        ]
        widgets = {
            "name":                   forms.TextInput(attrs={"class": "form-control"}),
            "output_type":            forms.Select(attrs={"class": "form-select"}),
            "real_weight_kg":         forms.NumberInput(attrs={"class": "form-control",
                                      "step": "0.001"}),
            "selling_price_ttc":      forms.NumberInput(attrs={"class": "form-control",
                                      "step": "0.01"}),
            "vat_rate":               forms.NumberInput(attrs={"class": "form-control",
                                      "step": "0.001"}),
            "linked_ingredient":      forms.Select(attrs={"class": "form-select"}),
            "parent_line":            forms.Select(attrs={"class": "form-select"}),
            "template_line":          forms.Select(attrs={"class": "form-select"}),
            "byproduct_selling_price": forms.NumberInput(attrs={"class": "form-control",
                                      "step": "0.01"}),
            "order":                  forms.NumberInput(attrs={"class": "form-control"}),
            "notes":                  forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, session=None, **kwargs):
        # Injecte la TVA par défaut dans initial si nouvelle instance
        if not kwargs.get('instance'):
            initial = kwargs.get('initial', {})
            if 'vat_rate' not in initial:
                initial['vat_rate'] = '0.0550'
            kwargs['initial'] = initial

        super().__init__(*args, **kwargs)
        from apps.catalog.models import Ingredient

        self.fields["linked_ingredient"].queryset = Ingredient.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["linked_ingredient"].required = False
        self.fields["linked_ingredient"].empty_label = "— Aucun —"
        self.fields["selling_price_ttc"].required = False
        self.fields["byproduct_selling_price"].required = False
        self.fields["byproduct_sold"].required = False
        self.fields["template_line"].required = False

        if session:
            qs = ButcheryLine.objects.filter(
                session=session
            ).order_by("order", "name")
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields["parent_line"].queryset = qs

            if session.template:
                self.fields["template_line"].queryset = \
                    CarcassTemplateLine.objects.filter(template=session.template)
            else:
                self.fields["template_line"].queryset = CarcassTemplateLine.objects.none()
        else:
            self.fields["parent_line"].queryset = ButcheryLine.objects.none()
            self.fields["template_line"].queryset = CarcassTemplateLine.objects.none()

        self.fields["parent_line"].required = False
        self.fields["parent_line"].empty_label = "— Pièce racine —"
        self.fields["template_line"].empty_label = "— Hors gabarit —"