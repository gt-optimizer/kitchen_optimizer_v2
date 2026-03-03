from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import PriceRecord


@receiver(post_save, sender=PriceRecord)
@receiver(post_delete, sender=PriceRecord)
def on_price_record_change(sender, instance, **kwargs):
    """
    Un prix d'achat change → recalcule toutes les recettes
    qui utilisent cet ingrédient.
    """
    if instance.ingredient:
        from apps.catalog.signals import on_ingredient_change
        on_ingredient_change(
            sender=instance.ingredient.__class__,
            instance=instance.ingredient,
        )