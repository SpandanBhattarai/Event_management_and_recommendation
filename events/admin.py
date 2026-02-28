from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe

from .models import Category, Event, UserPreference, Venue


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


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "favorite_category", "budget", "updated_at")
    search_fields = ("user__username", "user__email")
