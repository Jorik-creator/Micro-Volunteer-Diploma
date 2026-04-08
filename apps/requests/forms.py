"""
Forms for the requests app.

HelpRequestForm  — create / edit a HelpRequest (recipients only)
FilterForm       — filter the request list (volunteers)
ResponseForm     — optional message when responding to a request
"""

from django import forms
from django.utils import timezone

from .models import Category, HelpRequest, Response


class HelpRequestForm(forms.ModelForm):
    """Form for creating and editing help requests."""

    needed_date = forms.DateTimeField(
        label="Дата та час допомоги",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = HelpRequest
        fields = [
            "title",
            "description",
            "category",
            "urgency",
            "needed_date",
            "duration",
            "volunteers_needed",
            "address",
            "latitude",
            "longitude",
            "photo",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "latitude": forms.NumberInput(
                attrs={"step": "0.000001", "placeholder": "50.4501"}
            ),
            "longitude": forms.NumberInput(
                attrs={"step": "0.000001", "placeholder": "30.5234"}
            ),
        }
        labels = {
            "title": "Заголовок",
            "description": "Опис",
            "category": "Категорія",
            "urgency": "Терміновість",
            "duration": "Тривалість",
            "volunteers_needed": "Кількість волонтерів",
            "address": "Адреса",
            "latitude": "Широта",
            "longitude": "Довгота",
            "photo": "Фото (необов'язково)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.all()
        self.fields["category"].empty_label = "--- Оберіть категорію ---"

    def clean_needed_date(self):
        needed_date = self.cleaned_data.get("needed_date")
        if needed_date and needed_date < timezone.now():
            raise forms.ValidationError("Дата допомоги не може бути в минулому.")
        return needed_date

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "size"):
            if photo.size > 5 * 1024 * 1024:  # 5 MB
                raise forms.ValidationError("Розмір фото не повинен перевищувати 5 МБ.")
        return photo


class FilterForm(forms.Form):
    """Filter form for the help-request list (used by volunteers)."""

    category = forms.ModelChoiceField(
        label="Категорія",
        queryset=Category.objects.all(),
        required=False,
        empty_label="Всі категорії",
    )
    urgency = forms.ChoiceField(
        label="Терміновість",
        choices=[("", "Будь-яка")] + HelpRequest.Urgency.choices,
        required=False,
    )
    duration = forms.ChoiceField(
        label="Тривалість",
        choices=[("", "Будь-яка")] + HelpRequest.Duration.choices,
        required=False,
    )
    date_from = forms.DateField(
        label="Дата від",
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    date_to = forms.DateField(
        label="Дата до",
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )


class ResponseForm(forms.ModelForm):
    """Form for a volunteer to respond to a help request."""

    class Meta:
        model = Response
        fields = ["message"]
        widgets = {
            "message": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Коли зможете допомогти, ваш досвід тощо (необов'язково)...",
                }
            ),
        }
        labels = {"message": "Повідомлення (необов'язково)"}
