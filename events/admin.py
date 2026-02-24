from django import forms
from django.contrib import admin

from .models import Category, Event, Venue


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    pass


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
