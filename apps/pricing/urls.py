from django.urls import path
from . import views

app_name = "pricing"

urlpatterns = [
    # PRIX / ingrédients
    path("ingredients/<int:ingredient_pk>/prices/",
         views.ingredient_price_drawer, name="ingredient_price_drawer"),
    path("ingredients/<int:ingredient_pk>/prices/add/",
         views.ingredient_price_add, name="ingredient_price_add"),
    path("prices/<int:pk>/delete/",
         views.ingredient_price_delete, name="ingredient_price_delete"),

    # PRIX / recettes
    path("recipes/<int:pk>/price/drawer/", views.recipe_price_drawer, name="recipe_price_drawer"),
    path("recipes/<int:pk>/price/add/", views.recipe_price_add, name="recipe_price_add"),
    path("recipes/price/<int:price_pk>/delete/", views.recipe_price_delete, name="recipe_price_delete"),
]
