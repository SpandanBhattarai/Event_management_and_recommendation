from django import forms

from .models import Event


class OrganizerEventForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )
    end_date = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )

    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "venue",
            "category",
            "start_date",
            "end_date",
            "price",
            "popularity",
            "is_active",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")
        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError("End date must be after start date.")
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == "is_active":
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{existing} form-control".strip()
