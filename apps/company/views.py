from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.http import HttpResponse

from .mixins import require_role, check_role, get_current_company
from .models import Company, Employee, Equipment, StoragePlace, UserCompanyRole
from .forms import (
    CompanyForm, EmployeeForm, EmployeePublicForm,
    EquipmentForm, StoragePlaceForm, UserCompanyRoleForm,
)


# ══════════════════════════════════════════════════════════════════════════════
# COMPANY
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_role('owner', 'admin')
def company_list(request):
    companies = Company.objects.filter(tenant=request.tenant)
    return render(request, 'company/company_list.html', {
        'companies': companies,
    })


@login_required
@require_role('owner', 'admin')
def company_create(request):
    if request.method == 'POST':
        form = CompanyForm(request.POST)
        if form.is_valid():
            company = form.save(commit=False)
            company.tenant = request.tenant
            company.save()
            messages.success(request, f"Site « {company.name} » créé.")
            return redirect('company:company_detail', pk=company.pk)
    else:
        form = CompanyForm()
    return render(request, 'company/company_form.html', {
        'form': form, 'action': 'Nouveau site',
    })


@login_required
@require_role('owner', 'admin')
def company_detail(request, pk):
    company   = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    employees      = company.employees.all().order_by('last_name', 'first_name')
    equipment_list = company.equipment.filter(is_active=True).order_by('name')
    storage_places = company.storage_places.filter(is_active=True).order_by('name')
    user_roles     = company.user_roles.select_related('user').order_by('role')

    # Production voit les employés mais avec formulaire restreint
    can_see_financials = check_role(request, 'owner', 'admin')

    return render(request, 'company/company_detail.html', {
        'company':           company,
        'employees':         employees,
        'equipment_list':    equipment_list,
        'storage_places':    storage_places,
        'user_roles':        user_roles,
        'can_see_financials': can_see_financials,
    })


@login_required
@require_role('owner', 'admin')
def company_edit(request, pk):
    company = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, f"Site « {company.name} » mis à jour.")
            return redirect('company:company_detail', pk=company.pk)
    else:
        form = CompanyForm(instance=company)
    return render(request, 'company/company_form.html', {
        'form': form, 'action': 'Modifier le site', 'company': company,
    })


# ══════════════════════════════════════════════════════════════════════════════
# EMPLOYÉS — HTMX drawers
# Accès complet : owner, admin
# Accès restreint (lecture nom/prénom/tel) : production
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_role('owner', 'admin', 'production')
def employee_add(request, pk):
    company = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    is_full = check_role(request, 'owner', 'admin')
    FormClass = EmployeeForm if is_full else EmployeePublicForm

    if request.method == 'POST':
        form = FormClass(request.POST)
        if form.is_valid():
            employee = form.save(commit=False)
            employee.company = company
            employee.save()
            employees = company.employees.all().order_by('last_name', 'first_name')
            return render(request, 'company/partials/employee_list.html', {
                'company': company,
                'employees': employees,
                'can_see_financials': is_full,
            })
    else:
        form = FormClass()

    return render(request, 'company/partials/employee_drawer.html', {
        'form': form,
        'company': company,
        'form_action': request.path,
        'can_see_financials': is_full,
    })


@login_required
@require_role('owner', 'admin', 'production')
def employee_edit(request, pk, emp_pk):
    company  = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    employee = get_object_or_404(Employee, pk=emp_pk, company=company)
    is_full  = check_role(request, 'owner', 'admin')
    FormClass = EmployeeForm if is_full else EmployeePublicForm

    if request.method == 'POST':
        form = FormClass(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            employees = company.employees.all().order_by('last_name', 'first_name')
            return render(request, 'company/partials/employee_list.html', {
                'company': company,
                'employees': employees,
                'can_see_financials': is_full,
            })
    else:
        form = FormClass(instance=employee)

    return render(request, 'company/partials/employee_drawer.html', {
        'form': form,
        'company': company,
        'employee': employee,
        'form_action': request.path,
        'can_see_financials': is_full,
    })


@login_required
@require_role('owner', 'admin')
def employee_delete(request, pk, emp_pk):
    company  = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    employee = get_object_or_404(Employee, pk=emp_pk, company=company)
    if request.method == 'POST':
        employee.is_active = False
        employee.save(update_fields=['is_active'])
    employees = company.employees.all().order_by('last_name', 'first_name')
    return render(request, 'company/partials/employee_list.html', {
        'company': company,
        'employees': employees,
        'can_see_financials': True,
    })


# ══════════════════════════════════════════════════════════════════════════════
# ÉQUIPEMENTS — HTMX drawers
# Accès : owner, admin, production
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_role('owner', 'admin', 'production')
def equipment_add(request, pk):
    company = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = EquipmentForm(request.POST)
        if form.is_valid():
            eq = form.save(commit=False)
            eq.company = company
            eq.save()
            equipment_list = company.equipment.filter(is_active=True).order_by('name')
            return render(request, 'company/partials/equipment_list.html', {
                'company': company, 'equipment_list': equipment_list,
            })
    else:
        form = EquipmentForm()
    return render(request, 'company/partials/equipment_drawer.html', {
        'form': form, 'company': company, 'form_action': request.path,
    })


@login_required
@require_role('owner', 'admin', 'production')
def equipment_edit(request, pk, eq_pk):
    company   = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    equipment = get_object_or_404(Equipment, pk=eq_pk, company=company)
    if request.method == 'POST':
        form = EquipmentForm(request.POST, instance=equipment)
        if form.is_valid():
            form.save()
            equipment_list = company.equipment.filter(is_active=True).order_by('name')
            return render(request, 'company/partials/equipment_list.html', {
                'company': company, 'equipment_list': equipment_list,
            })
    else:
        form = EquipmentForm(instance=equipment)
    return render(request, 'company/partials/equipment_drawer.html', {
        'form': form, 'company': company, 'equipment': equipment,
        'form_action': request.path,
    })


@login_required
@require_role('owner', 'admin', 'production')
def equipment_delete(request, pk, eq_pk):
    company   = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    equipment = get_object_or_404(Equipment, pk=eq_pk, company=company)
    if request.method == 'POST':
        equipment.is_active = False
        equipment.save(update_fields=['is_active'])
    equipment_list = company.equipment.filter(is_active=True).order_by('name')
    return render(request, 'company/partials/equipment_list.html', {
        'company': company, 'equipment_list': equipment_list,
    })


# ══════════════════════════════════════════════════════════════════════════════
# LIEUX DE STOCKAGE — HTMX drawers
# Accès : owner, admin, production
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_role('owner', 'admin', 'production')
def storage_add(request, pk):
    company = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = StoragePlaceForm(request.POST)
        if form.is_valid():
            sp = form.save(commit=False)
            sp.company = company
            sp.save()
            storage_places = company.storage_places.filter(is_active=True).order_by('name')
            return render(request, 'company/partials/storage_list.html', {
                'company': company, 'storage_places': storage_places,
            })
    else:
        form = StoragePlaceForm()
    return render(request, 'company/partials/storage_drawer.html', {
        'form': form, 'company': company, 'form_action': request.path,
    })


@login_required
@require_role('owner', 'admin', 'production')
def storage_edit(request, pk, sp_pk):
    company = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    sp      = get_object_or_404(StoragePlace, pk=sp_pk, company=company)
    if request.method == 'POST':
        form = StoragePlaceForm(request.POST, instance=sp)
        if form.is_valid():
            form.save()
            storage_places = company.storage_places.filter(is_active=True).order_by('name')
            return render(request, 'company/partials/storage_list.html', {
                'company': company, 'storage_places': storage_places,
            })
    else:
        form = StoragePlaceForm(instance=sp)
    return render(request, 'company/partials/storage_drawer.html', {
        'form': form, 'company': company, 'storage_place': sp,
        'form_action': request.path,
    })


@login_required
@require_role('owner', 'admin', 'production')
def storage_delete(request, pk, sp_pk):
    company = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    sp      = get_object_or_404(StoragePlace, pk=sp_pk, company=company)
    if request.method == 'POST':
        sp.is_active = False
        sp.save(update_fields=['is_active'])
    storage_places = company.storage_places.filter(is_active=True).order_by('name')
    return render(request, 'company/partials/storage_list.html', {
        'company': company, 'storage_places': storage_places,
    })


# ══════════════════════════════════════════════════════════════════════════════
# UTILISATEURS / RÔLES — HTMX drawers
# Accès : owner uniquement
# ══════════════════════════════════════════════════════════════════════════════

@login_required
@require_role('owner')
def userrole_add(request, pk):
    company = get_object_or_404(Company, pk=pk, tenant=request.tenant)

    # Employés avec un compte user actif, pas encore dans les rôles du site
    existing_user_ids = company.user_roles.values_list('user_id', flat=True)
    employee_qs = Employee.objects.filter(
        company=company,
        is_active=True,
        user__isnull=False,          # a un compte
        user__is_active=True,        # compte actif
    ).exclude(
        user_id__in=existing_user_ids  # pas déjà dans les rôles
    ).select_related('user').order_by('last_name', 'first_name')

    if request.method == 'POST':
        form = UserCompanyRoleForm(request.POST, employee_qs=employee_qs)
        if form.is_valid():
            employee = form.cleaned_data['employee']
            role = form.save(commit=False)
            role.company = company
            role.user = employee.user
            role.save()

            user_roles = company.user_roles.select_related('user').order_by('role')
            return render(request, 'company/partials/userrole_list.html', {
                'company': company, 'user_roles': user_roles,
            })
    else:
        form = UserCompanyRoleForm(employee_qs=employee_qs)

    return render(request, 'company/partials/userrole_drawer.html', {
        'form': form, 'company': company, 'form_action': request.path,
    })


@login_required
@require_role('owner')
def userrole_delete(request, pk, role_pk):
    company   = get_object_or_404(Company, pk=pk, tenant=request.tenant)
    user_role = get_object_or_404(UserCompanyRole, pk=role_pk, company=company)
    if request.method == 'POST':
        user_role.delete()
    user_roles = company.user_roles.select_related('user').order_by('role')
    return render(request, 'company/partials/userrole_list.html', {
        'company': company, 'user_roles': user_roles,
    })

@login_required
def switch_company(request, pk):
    from apps.company.models import Company
    # Vérifie que le site existe (superuser voit tout, sinon filtre)
    if request.user.is_superuser:
        qs = Company.objects.all()
    else:
        qs = request.user.get_companies()
    if qs.filter(pk=pk).exists():
        request.session['current_company_id'] = pk
    return redirect(request.META.get('HTTP_REFERER', '/'))