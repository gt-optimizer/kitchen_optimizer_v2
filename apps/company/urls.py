from django.urls import path
from . import views

app_name = 'company'

urlpatterns = [
    # ── Sites ────────────────────────────────────────────────────────────────
    path('',                    views.company_list,   name='company_list'),
    path('add/',                views.company_create, name='company_create'),
    path('<int:pk>/',           views.company_detail, name='company_detail'),
    path('<int:pk>/edit/',      views.company_edit,   name='company_edit'),

    # ── Employés (HTMX drawers) ───────────────────────────────────────────
    path('<int:pk>/employees/add/',
         views.employee_add,    name='employee_add'),
    path('<int:pk>/employees/<int:emp_pk>/edit/',
         views.employee_edit,   name='employee_edit'),
    path('<int:pk>/employees/<int:emp_pk>/delete/',
         views.employee_delete, name='employee_delete'),

    # ── Équipements (HTMX drawers) ────────────────────────────────────────
    path('<int:pk>/equipment/add/',
         views.equipment_add,    name='equipment_add'),
    path('<int:pk>/equipment/<int:eq_pk>/edit/',
         views.equipment_edit,   name='equipment_edit'),
    path('<int:pk>/equipment/<int:eq_pk>/delete/',
         views.equipment_delete, name='equipment_delete'),

    # ── Lieux de stockage (HTMX drawers) ─────────────────────────────────
    path('<int:pk>/storage/add/',
         views.storage_add,    name='storage_add'),
    path('<int:pk>/storage/<int:sp_pk>/edit/',
         views.storage_edit,   name='storage_edit'),
    path('<int:pk>/storage/<int:sp_pk>/delete/',
         views.storage_delete, name='storage_delete'),

    # ── Utilisateurs / rôles (HTMX drawers) ──────────────────────────────
    path('<int:pk>/roles/add/',
         views.userrole_add,    name='userrole_add'),
    path('<int:pk>/roles/<int:role_pk>/delete/',
         views.userrole_delete, name='userrole_delete'),
]