from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0011_event_approval_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("role_changed", "Role Changed"),
                            ("user_activated", "User Activated"),
                            ("user_deactivated", "User Deactivated"),
                            ("event_approved", "Event Approved"),
                            ("event_rejected", "Event Rejected"),
                        ],
                        max_length=40,
                    ),
                ),
                ("details", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="performed_audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="events.event",
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="targeted_audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ticket_purchase",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="events.ticketpurchase",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
