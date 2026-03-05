from django import forms
from .models import Company, Employee, Equipment, StoragePlace, UserCompanyRole


class CompanyForm(forms.ModelForm):
    class Meta:
        model  = Company
        fields = [
            'name', 'company_type', 'address', 'zipcode', 'city',
            'phone', 'email', 'siret', 'vat_number', 'is_active',
        ]
        widgets = {
            'name':         forms.TextInput(attrs={'class': 'form-control'}),
            'company_type': forms.Select(attrs={'class': 'form-select'}),
            'address':      forms.TextInput(attrs={'class': 'form-control'}),
            'zipcode':      forms.TextInput(attrs={'class': 'form-control'}),
            'city':         forms.TextInput(attrs={'class': 'form-control'}),
            'phone':        forms.TextInput(attrs={'class': 'form-control'}),
            'email':        forms.EmailInput(attrs={'class': 'form-control'}),
            'siret':        forms.TextInput(attrs={'class': 'form-control'}),
            'vat_number':   forms.TextInput(attrs={'class': 'form-control'}),
        }


class EmployeeForm(forms.ModelForm):
    class Meta:
        model  = Employee
        fields = [
            'first_name', 'last_name', 'job_title',
            'phone', 'email',
            'hourly_cost', 'weekly_hours',
            'is_active',
        ]
        widgets = {
            'first_name':   forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':    forms.TextInput(attrs={'class': 'form-control'}),
            'job_title':    forms.TextInput(attrs={'class': 'form-control'}),
            'phone':        forms.TextInput(attrs={'class': 'form-control'}),
            'email':        forms.EmailInput(attrs={'class': 'form-control'}),
            'hourly_cost':  forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'weekly_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
            'is_active':    forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['is_active'].initial = True


class EmployeePublicForm(forms.ModelForm):
    class Meta:
        model  = Employee
        fields = ['first_name', 'last_name', 'job_title', 'phone', 'is_active']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'job_title':  forms.TextInput(attrs={'class': 'form-control'}),
            'phone':      forms.TextInput(attrs={'class': 'form-control'}),
            'is_active':  forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['is_active'].initial = True



class EquipmentForm(forms.ModelForm):
    class Meta:
        model  = Equipment
        fields = ['name', 'description', 'capacity', 'capacity_unit', 'is_active']
        widgets = {
            'name':          forms.TextInput(attrs={'class': 'form-control'}),
            'description':   forms.TextInput(attrs={'class': 'form-control'}),
            'capacity':      forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'capacity_unit': forms.Select(attrs={'class': 'form-select'}),
        }


class StoragePlaceForm(forms.ModelForm):
    class Meta:
        model  = StoragePlace
        fields = ['name', 'temperature', 'is_active']
        widgets = {
            'name':        forms.TextInput(attrs={'class': 'form-control'}),
            'temperature': forms.Select(attrs={'class': 'form-select'}),
        }


class UserCompanyRoleForm(forms.ModelForm):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        required=True,
        empty_label="— Sélectionner un employé —",
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Employé",
    )

    class Meta:
        model  = UserCompanyRole
        fields = ['role']
        widgets = {
            'role': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, employee_qs=None, **kwargs):
        # Supprime company des kwargs si présent (compatibilité)
        kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if employee_qs is not None:
            self.fields['employee'].queryset = employee_qs