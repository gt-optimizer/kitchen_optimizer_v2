from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import PriceRecord


@receiver(post_save, sender=PriceRecord)
@receiver(post_delete, sender=PriceRecord)
def on_price_record_change(sender, instance, **kwargs):
    if instance.ingredient:
        from apps.catalog.signals import _recompute_recipe, _propagate_to_parents
        from apps.catalog.models import RecipeLine, Recipe
        direct_recipe_ids = (
            RecipeLine.objects
            .filter(ingredient=instance.ingredient)
            .values_list("recipe_id", flat=True)
            .distinct()
        )
        for recipe in Recipe.objects.filter(pk__in=direct_recipe_ids):
            _recompute_recipe(recipe)
            _propagate_to_parents(recipe)