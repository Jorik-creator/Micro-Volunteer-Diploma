"""
Forms for the reviews app.

ReviewForm — оцінка іншої сторони після завершення запиту.
"""

from django import forms

from .models import Review


class ReviewForm(forms.Form):
    """Зірки 1–5, теги залежно від ролі того, кого оцінюють, і необов'язковий коментар."""

    rating = forms.TypedChoiceField(
        label="Оцінка",
        choices=[(i, str(i)) for i in range(5, 0, -1)],
        coerce=int,
        widget=forms.RadioSelect,
        error_messages={"required": "Оберіть оцінку від 1 до 5."},
    )
    tags = forms.MultipleChoiceField(
        label="Що запам'яталося",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    comment = forms.CharField(
        label="Коментар (необов'язково)",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 1000}),
    )

    def __init__(self, *args, target, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = Review.VOLUNTEER_TAGS if target.is_volunteer else Review.RECIPIENT_TAGS
        labels = dict(Review.Tag.choices)
        self.fields["tags"].choices = [(tag.value, labels[tag]) for tag in allowed]
