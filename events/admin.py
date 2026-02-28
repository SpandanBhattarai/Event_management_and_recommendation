from django import forms
from django.contrib import admin
from django.utils import timezone
from django.utils.safestring import mark_safe

from .models import AuditLog, Category, Event, UserPreference, UserRole, Venue


class VenueAdminForm(forms.ModelForm):
    class Meta:
        model = Venue
        fields = "__all__"

    class Media:
        css = {
            "all": ("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",),
        }
        js = (
            "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
            "js/admin_venue_map.js",
        )

@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    form = VenueAdminForm
    list_display = ("name", "city", "capacity", "latitude", "longitude")
    search_fields = ("name", "city", "address")
    readonly_fields = ("map_picker",)
    fields = ("name", "address", "city", "capacity", "map_picker", "latitude", "longitude")

    def map_picker(self, obj):
        return mark_safe(
            """
            <div style="margin-top: 4px; margin-bottom: 8px;">
              <input id="venue-map-search" type="text" placeholder="Search place or address" style="width: 320px; max-width: 100%; padding: 6px 8px;">
              <button id="venue-map-search-btn" type="button" style="margin-left: 6px; padding: 6px 10px;">Search</button>
              <small style="display: block; margin-top: 6px;">Click map or drag marker to set latitude and longitude.</small>
            </div>
            <div id="venue-map" style="height: 340px; border-radius: 8px; border: 1px solid #d9d9d9;"></div>
            """
        )
    map_picker.short_description = "Venue Location"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    pass


class EventAdminForm(forms.ModelForm):
    popularity = forms.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Event
        fields = "__all__"


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventAdminForm
    list_display = (
        "title",
        "organizer",
        "approval_status",
        "approved_by",
        "venue",
        "category",
        "start_date",
        "is_active",
    )
    list_filter = ("approval_status", "is_active", "category", "venue__city", "organizer")
    search_fields = ("title", "description", "venue__name", "organizer__username")

    def save_model(self, request, obj, form, change):
        if not obj.organizer and request.user.is_authenticated:
            obj.organizer = request.user
        if obj.approval_status == Event.APPROVAL_APPROVED and not obj.approved_by:
            obj.approved_by = request.user
        if obj.approval_status == Event.APPROVAL_APPROVED and not obj.approved_at:
            obj.approved_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "favorite_category", "budget", "updated_at")
    search_fields = ("user__username", "user__email")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "updated_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target_user", "event", "ticket_purchase")
    list_filter = ("action", "created_at")
    search_fields = (
        "actor__username",
        "target_user__username",
        "event__title",
        "ticket_purchase__purchase_order_id",
    )
    readonly_fields = ("actor", "action", "target_user", "event", "ticket_purchase", "details", "created_at")
