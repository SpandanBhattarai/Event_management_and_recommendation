from django.db import migrations, models
from django.db.models import Q


def clamp_popularity(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    Event.objects.filter(popularity__lt=1).update(popularity=1)
    Event.objects.filter(popularity__gt=5).update(popularity=5)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0004_ticketpurchase"),
    ]

    operations = [
        migrations.RunPython(clamp_popularity, noop_reverse),
        migrations.AddConstraint(
            model_name="event",
            constraint=models.CheckConstraint(
                condition=Q(popularity__gte=1, popularity__lte=5),
                name="event_popularity_1_5",
            ),
        ),
    ]
