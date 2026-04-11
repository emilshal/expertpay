from django.contrib.auth.hashers import make_password
from django.db import migrations


def seed_newtech_owner(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Fleet = apps.get_model("accounts", "Fleet")
    FleetPhoneBinding = apps.get_model("accounts", "FleetPhoneBinding")

    fleet, _ = Fleet.objects.get_or_create(name="New Tech")
    user, _ = User.objects.get_or_create(
        username="newtech_owner_demo",
        defaults={
            "first_name": "New Tech",
            "last_name": "Owner",
            "password": make_password("changeme123"),
            "is_active": True,
        },
    )

    binding, _ = FleetPhoneBinding.objects.get_or_create(
        phone_number="598950003",
        defaults={
            "fleet": fleet,
            "user": user,
            "role": "owner",
            "is_active": True,
        },
    )
    updates = []
    if binding.fleet_id != fleet.id:
        binding.fleet = fleet
        updates.append("fleet")
    if binding.user_id != user.id:
        binding.user = user
        updates.append("user")
    if binding.role != "owner":
        binding.role = "owner"
        updates.append("role")
    if not binding.is_active:
        binding.is_active = True
        updates.append("is_active")
    if updates:
        binding.save(update_fields=updates + ["updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_driverfleetmembership"),
    ]

    operations = [
        migrations.RunPython(seed_newtech_owner, migrations.RunPython.noop),
    ]
