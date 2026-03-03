from django.urls import path
from . import views

app_name = "pricing"

urlpatterns = [
    path("ingredients/<int:ingredient_pk>/prices/",
         views.ingredient_price_drawer, name="ingredient_price_drawer"),
    path("ingredients/<int:ingredient_pk>/prices/add/",
         views.ingredient_price_add, name="ingredient_price_add"),
    path("prices/<int:pk>/delete/",
         views.ingredient_price_delete, name="ingredient_price_delete"),
]
