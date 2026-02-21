from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import get_or_create_user_ledger_account


@receiver(post_save, sender=User)
def create_user_ledger_account(sender, instance, created, **kwargs):
    if created:
        get_or_create_user_ledger_account(instance)
