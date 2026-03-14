from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0013_userpreference_preferred_city_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticketpurchase",
            name="reservation_expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
