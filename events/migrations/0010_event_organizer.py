from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_event_organizer(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    target_user = User.objects.filter(username__iexact="spandan").first()
    if not target_user:
        target_user = User.objects.filter(is_superuser=True).order_by("id").first()
    if not target_user:
        target_user = User.objects.order_by("id").first()
    if not target_user:
        return

    Event.objects.filter(organizer__isnull=True).update(organizer=target_user)


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0009_userrole"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="organizer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="organized_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_event_organizer, migrations.RunPython.noop),
    ]
