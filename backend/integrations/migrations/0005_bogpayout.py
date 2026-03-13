from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("wallet", "0003_bankaccount_beneficiary_inn"),
        ("integrations", "0004_yandexsyncrun_yandextransactioncategory"),
    ]

    operations = [
        migrations.CreateModel(
            name="BogPayout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider_unique_id", models.CharField(blank=True, max_length=120)),
                ("provider_unique_key", models.BigIntegerField(blank=True, null=True, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("accepted", "Accepted"),
                            ("processing", "Processing"),
                            ("settled", "Settled"),
                            ("failed", "Failed"),
                            ("reversed", "Reversed"),
                        ],
                        default="accepted",
                        max_length=20,
                    ),
                ),
                ("provider_status", models.CharField(blank=True, max_length=120)),
                ("result_code", models.IntegerField(blank=True, null=True)),
                ("match_score", models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ("failure_reason", models.CharField(blank=True, max_length=255)),
                ("request_payload", models.JSONField(blank=True, default=dict)),
                ("response_payload", models.JSONField(blank=True, default=dict)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("last_status_checked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bog_payouts",
                        to="integrations.providerconnection",
                    ),
                ),
                (
                    "withdrawal",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bog_payout",
                        to="wallet.withdrawalrequest",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
