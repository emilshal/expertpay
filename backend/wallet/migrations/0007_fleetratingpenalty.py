from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_seed_newtech_owner"),
        ("wallet", "0006_withdrawalrequest_fee_amount_withdrawalrequest_fleet"),
    ]

    operations = [
        migrations.CreateModel(
            name="FleetRatingPenalty",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "reason",
                    models.CharField(
                        choices=[("insufficient_reserve", "Insufficient Reserve")],
                        default="insufficient_reserve",
                        max_length=32,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "fleet",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rating_penalties", to="accounts.fleet"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fleet_rating_penalties",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
