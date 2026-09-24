from django import forms

from .models import EmailPreferences


class EmailPreferencesForm(forms.ModelForm):
    class Meta:
        model = EmailPreferences
        fields = ["responses", "lifecycle", "messages", "reviews", "nearby", "account"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-check-input", "role": "switch"})
