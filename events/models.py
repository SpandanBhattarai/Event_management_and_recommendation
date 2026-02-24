from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings


class Venue(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField()
    capacity = models.IntegerField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    city = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Category(models.Model):
    name = models.CharField(max_length=100)  # e.g., Concert, Conference, Sports

    def __str__(self):
        return self.name

class Event(models.Model):  
    title = models.CharField(max_length=200)
    description = models.TextField()
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    # Fields for scoring
    popularity = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )  # 1-5 scale
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(popularity__gte=1, popularity__lte=5),
                name="event_popularity_1_5",
            )
        ]

    def __str__(self):
        return self.title


class UserPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    favorite_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_preferences",
    )
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences for {self.user.username}"


class TicketPurchase(models.Model):
    STATUS_INITIATED = "initiated"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELED = "canceled"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_INITIATED, "Initiated"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELED, "Canceled"),
        (STATUS_FAILED, "Failed"),
    ]

    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="ticket_purchases")
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="ticket_purchases")
    quantity = models.PositiveIntegerField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INITIATED)
    khalti_pidx = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    khalti_txn_id = models.CharField(max_length=120, blank=True, null=True)
    purchase_order_id = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.event.title} ({self.quantity})"

