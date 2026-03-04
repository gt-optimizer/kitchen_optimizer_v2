from django.urls import path
from . import views

app_name = "purchasing"

urlpatterns = [
    # Fournisseurs
    path("suppliers/",              views.supplier_list,   name="supplier_list"),
    path("suppliers/add/",          views.supplier_add,    name="supplier_add"),
    path("suppliers/<int:pk>/",     views.supplier_detail, name="supplier_detail"),
    path("suppliers/<int:pk>/edit/",views.supplier_edit,   name="supplier_edit"),

    # Documents (BL/factures)
    path("documents/",                      views.document_list,   name="document_list"),
    path("documents/upload/",               views.document_upload, name="document_upload"),
    path("documents/<int:pk>/",             views.document_detail, name="document_detail"),
    path("documents/<int:pk>/parse/",       views.document_parse,  name="document_parse"),
    path("documents/<int:pk>/validate/",    views.document_validate, name="document_validate"),
    path("documents/<int:pk>/lines/<int:line_pk>/confirm/",
         views.document_line_confirm, name="document_line_confirm"),
    path("documents/<int:pk>/lines/<int:line_pk>/match/",
         views.document_line_match,   name="document_line_match"),
    path("documents/<int:pk>/supplier/create/",
         views.supplier_add_from_doc, name="supplier_add_from_doc"),
    path("documents/<int:pk>/lines/<int:line_pk>/create-ingredient/",
         views.ingredient_create_from_line, name="ingredient_create_from_line"),
]