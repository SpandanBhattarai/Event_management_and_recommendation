from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_user_roles(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    UserRole = apps.get_model("events", "UserRole")

    for user in User.objects.all():
        role = "user"
        if user.is_superuser or user.username.lower() == "spandan":
            role = "admin"
        UserRole.objects.update_or_create(user=user, defaults={"role": role})


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0008_userpreference"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("admin", "Admin"), ("organizer", "Organizer"), ("user", "User")], default="user", max_length=20)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="role_profile", to=settings.AUTH_USER_MODEL),
                ),
            ],
        ),
        migrations.RunPython(seed_user_roles, migrations.RunPython.noop),
    ]
