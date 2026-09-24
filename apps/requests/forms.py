"""
Forms for the requests app.

HelpRequestForm  — create / edit a HelpRequest (recipients only)
FilterForm       — filter the request list (volunteers)
ResponseForm     — optional message when responding to a request
"""

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from apps.core.images import REQUEST_PHOTO_MAX, shrink

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
            "help_format",
            "urgency",
            "needed_date",
            "duration",
            "volunteers_needed",
            "on_behalf",
            "beneficiary_name",
            "beneficiary_phone",
            "city",
            "address",
            "latitude",
            "longitude",
            "photo",
        ]
        widgets = {
            "help_format": forms.RadioSelect,
            "description": forms.Textarea(attrs={"rows": 4}),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
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

    def clean(self):
        cleaned = super().clean()
        remote = cleaned.get("help_format") == HelpRequest.HelpFormat.REMOTE
        if remote:
            # Online help needs no address and must not appear on the map
            cleaned["city"] = ""
            cleaned["address"] = ""
            cleaned["latitude"] = None
            cleaned["longitude"] = None
        else:
            if not cleaned.get("address"):
                self.add_error("address", "Вкажіть адресу — її побачить лише прийнятий волонтер.")
            if not cleaned.get("city"):
                self.add_error("city", "Вкажіть місто — його бачитимуть волонтери у списку.")
        if cleaned.get("on_behalf"):
            if not cleaned.get("beneficiary_name"):
                self.add_error("beneficiary_name", "Вкажіть, кому потрібна допомога.")
            if not cleaned.get("beneficiary_phone"):
                self.add_error(
                    "beneficiary_phone", "Потрібен телефон — волонтер зателефонує перед візитом."
                )
        else:
            cleaned["beneficiary_name"] = ""
            cleaned["beneficiary_phone"] = ""
        return cleaned

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if isinstance(photo, UploadedFile):
            if photo.size > 5 * 1024 * 1024:  # 5 MB before compression
                raise forms.ValidationError("Розмір фото не повинен перевищувати 5 МБ.")
            photo = shrink(photo, REQUEST_PHOTO_MAX)
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
        choices=[("", "Будь-яка"), *HelpRequest.Urgency.choices],
        required=False,
    )
    duration = forms.ChoiceField(
        label="Тривалість",
        choices=[("", "Будь-яка"), *HelpRequest.Duration.choices],
        required=False,
    )
    help_format = forms.ChoiceField(
        label="Формат допомоги",
        choices=[("", "Будь-який"), *HelpRequest.HelpFormat.choices],
        required=False,
    )
    city = forms.CharField(
        label="Місто",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Київ, Львів..."}),
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
    # Only applied for signed-in volunteers (see HelpRequestListView)
    can_take = forms.BooleanField(
        label="Лише ті, на які я можу відгукнутися",
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


class ReasonForm(forms.Form):
    """Short explanation for withdrawing, removing a volunteer or disputing completion."""

    reason = forms.CharField(
        label="Причина",
        max_length=300,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "maxlength": 300}),
        error_messages={"max_length": "Причина задовга — не більше %(limit_value)d символів."},
    )
