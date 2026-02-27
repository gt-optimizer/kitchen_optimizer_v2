from django.urls import path
from . import views

app_name = "catalog"

urlpatterns = [
    # Ingrédients
    path("ingredients/", views.ingredient_list, name="ingredient_list"),
    path("ingredients/add/", views.ingredient_create, name="ingredient_create"),
    path("ingredients/<int:pk>/", views.ingredient_detail, name="ingredient_detail"),
    path("ingredients/<int:pk>/edit/", views.ingredient_edit, name="ingredient_edit"),
    path("ingredients/<int:pk>/delete/", views.ingredient_delete, name="ingredient_delete"),
    # HTMX
    path("ingredients/search/", views.ingredient_search_htmx, name="ingredient_search"),
]