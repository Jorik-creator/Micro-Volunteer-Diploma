"""
Forms for the reviews app.

ReviewForm — залишити відгук після виконання запиту допомоги.
"""

from django import forms

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout, Submit

from .models import Review


class ReviewForm(forms.ModelForm):
    """Форма для створення відгуку (оцінка 1–5 та коментар)."""

    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            # Числове поле з обмеженням min/max на рівні HTML-атрибутів
            "rating": forms.NumberInput(
                attrs={
                    "min": 1,
                    "max": 5,
                    "class": "form-control",
                }
            ),
            # Текстова область для коментаря
            "comment": forms.Textarea(
                attrs={
                    "class": "form-control",
                }
            ),
        }
        labels = {
            "rating": "Оцінка (1-5)",
            "comment": "Коментар",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Налаштування crispy-forms: метод POST та макет полів
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Field("rating"),
            Field("comment"),
            Submit("submit", "Надіслати відгук", css_class="btn btn-primary mt-2"),
        )

    def clean_rating(self):
        """Перевірка, що оцінка знаходиться в діапазоні 1–5."""
        rating = self.cleaned_data.get("rating")
        if rating is not None and not (1 <= rating <= 5):
            raise forms.ValidationError("Оцінка повинна бути від 1 до 5.")
        return rating
