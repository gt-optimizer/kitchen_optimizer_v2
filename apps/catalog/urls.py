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
    path("ingredients/search/", views.ingredient_search_htmx, name="ingredient_search"),

    # Recettes
    path("recipes/", views.recipe_list, name="recipe_list"),
    path("recipes/add/", views.recipe_create, name="recipe_create"),
    path("recipes/<int:pk>/", views.recipe_detail, name="recipe_detail"),
    path("recipes/<int:pk>/edit/", views.recipe_edit, name="recipe_edit"),
    path("recipes/<int:pk>/delete/", views.recipe_delete, name="recipe_delete"),
    # HTMX recettes
    path("recipes/search/", views.recipe_search_htmx, name="recipe_search"),
    path("recipes/<int:pk>/lines/add/", views.recipe_line_add_htmx, name="recipe_line_add"),
    path("recipes/lines/<int:line_pk>/delete/", views.recipe_line_delete_htmx, name="recipe_line_delete"),
    path("recipes/ingredient-cost/", views.ingredient_cost_htmx, name="ingredient_cost"),
]