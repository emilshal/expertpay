from django.db import migrations


def seed_more_fleets(apps, schema_editor):
    Fleet = apps.get_model("accounts", "Fleet")

    sample_fleets = [
        "New Tech",
        "Tbilisi Express",
        "Capital Ride",
        "Rustavi Mobility",
        "Batumi Drivers Union",
        "Kutaisi Fleet Group",
    ]

    for fleet_name in sample_fleets:
        Fleet.objects.get_or_create(name=fleet_name)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_seed_demo_fleet_data"),
    ]

    operations = [
        migrations.RunPython(seed_more_fleets, migrations.RunPython.noop),
    ]
