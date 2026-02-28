from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserRole


User = get_user_model()


@receiver(post_save, sender=User)
def ensure_user_role(sender, instance, created, **kwargs):
    if not created:
        return

    role = UserRole.ROLE_USER
    if instance.is_superuser or instance.username.lower() == "spandan":
        role = UserRole.ROLE_ADMIN
    UserRole.objects.get_or_create(user=instance, defaults={"role": role})
