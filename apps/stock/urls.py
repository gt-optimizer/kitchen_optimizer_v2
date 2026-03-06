from django.urls import path
from . import views

app_name = "stock"

urlpatterns = [
    # Dashboard
    path("",                                          views.stock_dashboard,      name="dashboard"),

    # Lots
    path("batches/",                                  views.batch_list,           name="batch_list"),
    path("batches/<int:pk>/edit/",                    views.batch_edit,           name="batch_edit"),

    # Mouvements
    path("movements/",                                views.movement_list,        name="movement_list"),
    path("corrections/add/",                          views.correction_add,       name="correction_add"),

    # Inventaires
    path("inventories/",                              views.inventory_list,       name="inventory_list"),
    path("inventories/add/",                          views.inventory_create,     name="inventory_create"),
    path("inventories/<int:pk>/",                     views.inventory_detail,     name="inventory_detail"),
    path("inventories/<int:pk>/validate/",            views.inventory_validate,   name="inventory_validate"),
    path("inventories/<int:pk>/lines/<int:lpk>/edit/",views.inventory_line_edit,  name="inventory_line_edit"),
    path("inventories/<int:pk>/lines/add/", views.inventory_line_add, name="inventory_line_add"),

    # Transferts internes
    path("transfers/",                                views.transfer_list,        name="transfer_list"),
    path("transfers/add/",                            views.transfer_create,      name="transfer_create"),
    path("transfers/<int:pk>/",                       views.transfer_detail,      name="transfer_detail"),
    path("transfers/<int:pk>/send/",                  views.transfer_send,        name="transfer_send"),
    path("transfers/<int:pk>/receive/",               views.transfer_receive,     name="transfer_receive"),
    path("transfers/<int:pk>/lines/add/",             views.transfer_line_add,    name="transfer_line_add"),
    path("transfers/<int:pk>/lines/<int:lpk>/delete/",views.transfer_line_delete, name="transfer_line_delete"),
    path("ingredients/search/", views.ingredient_search_htmx, name="ingredient_search"),
]