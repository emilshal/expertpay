from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wallet", "0002_bankaccount_transaction_withdrawalrequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="bankaccount",
            name="beneficiary_inn",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
