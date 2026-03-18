from django.db.models.signals import post_save
from django.dispatch import receiver

from ledger.services import get_or_create_driver_available_account, get_or_create_fleet_reserve_account

from .models import DriverFleetMembership, Fleet


@receiver(post_save, sender=Fleet)
def ensure_fleet_reserve_account(sender, instance, created, **kwargs):
    if created:
        get_or_create_fleet_reserve_account(instance)


@receiver(post_save, sender=DriverFleetMembership)
def ensure_driver_available_account(sender, instance, created, **kwargs):
    if created:
        get_or_create_driver_available_account(instance.user, fleet=instance.fleet)
