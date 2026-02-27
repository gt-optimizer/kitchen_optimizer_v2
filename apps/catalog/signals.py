from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Ingredient


@receiver(post_save, sender=Ingredient)
def trigger_label_ocr(sender, instance, created, update_fields, **kwargs):
    """
    Déclenche l'OCR automatiquement quand label_photo est modifié.
    """
    # Évite les boucles infinies
    if update_fields and "label_photo" not in update_fields:
        return

    if instance.label_photo:
        from .services.label_ocr import run_label_ocr
        try:
            result = run_label_ocr(instance)
            # Stocke le résultat en cache pour l'afficher dans la vue
            from django.core.cache import cache
            cache.set(f"ocr_result_{instance.pk}", result, timeout=300)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"OCR signal erreur : {e}")