from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_driverfleetmembership"),
        ("integrations", "0006_alter_providerconnection_provider_bogcardorder"),
    ]

    operations = [
        migrations.AddField(
            model_name="bogcardorder",
            name="fleet",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bog_card_orders",
                to="accounts.fleet",
            ),
        ),
    ]
