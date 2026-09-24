from django import forms

from .models import InviteCode, Report, VerificationRequest


class VerificationForm(forms.ModelForm):
    contact_link = forms.URLField(
        label="Соцмережа або сторінка організації",
        required=False,
        assume_scheme="https",
        help_text="Необов'язково. Допомагає модератору переконатися, що ви реальна людина.",
    )

    class Meta:
        model = VerificationRequest
        fields = ["city", "about", "contact_link", "organization", "video_call_ok"]
        widgets = {"about": forms.Textarea(attrs={"rows": 5, "maxlength": 1500})}
        help_texts = {
            "about": "Волонтерам: чому хочете допомагати, який маєте досвід. "
            "Отримувачам: яка допомога вам потрібна і чому. Документи не потрібні.",
            "organization": "Якщо ви волонтер організації чи соцпрацівник.",
        }


class InviteRedeemForm(forms.Form):
    code = forms.CharField(
        label="Код організації",
        max_length=20,
        widget=forms.TextInput(attrs={"autocomplete": "off", "placeholder": "Напр. K7PM3XQ2RA"}),
    )


class DecisionForm(forms.Form):
    note = forms.CharField(
        label="Причина / коментар",
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class ReportForm(forms.Form):
    reason = forms.ChoiceField(label="Що сталося?", choices=Report.Reason.choices)
    comment = forms.CharField(
        label="Подробиці (необов'язково)",
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class InviteCodeForm(forms.ModelForm):
    class Meta:
        model = InviteCode
        fields = ["organization", "max_uses", "expires_at"]
        widgets = {"expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}
