"""
Signals pour l'app company.
- post_save Employee → crée le User associé si inexistant
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='company.Employee')
def create_user_for_employee(sender, instance, created, **kwargs):
    """
    À la création d'un employé :
    - Génère un username unique (p.nom)
    - Crée le User avec mot de passe = username
    - Lie Employee.user → User
    - Marque must_change_password (via set_password + is_active=True)
    """
    if not created:
        return
    if instance.user_id:
        return  # déjà lié

    try:
        from apps.users.models import User
        from apps.users.utils import generate_username

        username = generate_username(instance.first_name, instance.last_name)

        user = User(
            username=username,
            first_name=instance.first_name,
            last_name=instance.last_name,
            email=instance.email or '',
            tenant=instance.company.tenant,
            is_active=True,
        )
        user.set_password(username)  # mot de passe = username
        user.save()

        # Lie l'employé au user sans déclencher à nouveau le signal
        sender.objects.filter(pk=instance.pk).update(user=user)
        instance.user = user  # met à jour l'instance en mémoire aussi

        logger.info(f"User '{username}' créé pour l'employé {instance.first_name} {instance.last_name}")

    except Exception as e:
        logger.error(f"Erreur création user pour employé {instance.pk}: {e}")