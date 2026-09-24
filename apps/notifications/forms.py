from django import forms

from .models import EmailPreferences

HELP_TEXTS = {
    "lifecycle": "Виконання, скасування запиту й нагадування перед допомогою",
    "messages": "Коли в розмові з'являється нове повідомлення",
    "reviews": "Коли вас оцінили або настав час залишити оцінку",
    "nearby": "Нові запити у вашому радіусі — буває кілька на день",
    "account": "Перевірка профілю та рішення модераторів",
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
            field.help_text = (
                RESPONSES_HELP.get(role, "") if name == "responses" else HELP_TEXTS[name]
            )
            field.widget.attrs.update({"class": "form-check-input", "role": "switch"})
