from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0012_auditlog"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="userpreference",
                    name="preferred_city",
                    field=models.CharField(blank=True, default="", max_length=100),
                ),
            ],
            database_operations=[],
        ),
    ]
