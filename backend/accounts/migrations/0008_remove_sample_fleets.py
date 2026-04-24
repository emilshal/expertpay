from django.db import migrations


def remove_sample_fleets(apps, schema_editor):
    Fleet = apps.get_model("accounts", "Fleet")
    sample_fleets = [
        "Tbilisi Express",
        "Capital Ride",
        "Rustavi Mobility",
        "Batumi Drivers Union",
        "Kutaisi Fleet Group",
    ]
    Fleet.objects.filter(name__in=sample_fleets).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_logincodechallenge_provider_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_sample_fleets, migrations.RunPython.noop),
    ]
