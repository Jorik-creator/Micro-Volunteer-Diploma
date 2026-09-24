from django import forms

from .models import EmailPreferences

LABELS = {
    "responses": "Відгуки волонтерів",
    "lifecycle": "Хід запиту",
    "messages": "Повідомлення в розмовах",
    "reviews": "Оцінки",
    "nearby": "Запити поблизу",
    "account": "Профіль і модерація",
}
HELP_TEXTS = {
    "lifecycle": "Допомогу позначено виконаною, запит скасовано чи прострочено, нагадування",
    "messages": "Коли вам пишуть у розмові щодо запиту (не частіше разу на 10 хвилин)",
    "reviews": "Коли вас оцінили або настав час оцінити іншу сторону",
    "nearby": "Нові запити у вашому радіусі й категоріях — буває кілька на день",
    "account": "Рішення щодо перевірки профілю, модерації запитів і ваших скарг",
}
RESPONSES_HELP = {
    "recipient": "Коли волонтер відгукується на ваш запит",
    "volunteer": "Коли вас прийняли або обрали іншого волонтера",
}


class EmailPreferencesForm(forms.ModelForm):
    """
    Email switches worded for the user's role. Recipients never get nearby
    requests, so the switch is hidden for them (the stored value is kept).
    """

    class Meta:
        model = EmailPreferences
        fields = ["responses", "lifecycle", "messages", "reviews", "nearby", "account"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        role = getattr(user, "user_type", None)
        if user is not None and user.is_recipient:
            del self.fields["nearby"]
        for name, field in self.fields.items():
            field.label = LABELS.get(name, field.label)
            field.help_text = (
                RESPONSES_HELP.get(role, "") if name == "responses" else HELP_TEXTS[name]
            )
            field.widget.attrs.update({"class": "form-check-input", "role": "switch"})
