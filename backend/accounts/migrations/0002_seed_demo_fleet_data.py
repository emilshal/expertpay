from django.contrib.auth.hashers import make_password
from django.db import migrations


def seed_demo_data(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Fleet = apps.get_model("accounts", "Fleet")
    FleetPhoneBinding = apps.get_model("accounts", "FleetPhoneBinding")

    user, _ = User.objects.get_or_create(
        username="newtech_demo",
        defaults={
            "password": make_password("changeme123"),
            "is_active": True,
        },
    )
    fleet, _ = Fleet.objects.get_or_create(name="New Tech")
    FleetPhoneBinding.objects.get_or_create(
        fleet=fleet,
        phone_number="+995555000111",
        defaults={"user": user, "is_active": True},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_demo_data, migrations.RunPython.noop),
    ]
