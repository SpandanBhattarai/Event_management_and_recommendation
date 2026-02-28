from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_approved_events(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    approver = User.objects.filter(username__iexact="spandan").first()
    if not approver:
        approver = User.objects.filter(is_superuser=True).order_by("id").first()
    if not approver:
        approver = User.objects.order_by("id").first()

    updates = {"approval_status": "approved"}
    if approver:
        updates["approved_by"] = approver
    Event.objects.filter(approval_status="pending").update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0010_event_organizer"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="approval_status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_approved_events, migrations.RunPython.noop),
    ]
