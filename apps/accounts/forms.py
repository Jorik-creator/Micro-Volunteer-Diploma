from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.forms import (
    PasswordChangeForm as DjangoPasswordChangeForm,
)
from django.contrib.auth.forms import (
    PasswordResetForm as DjangoPasswordResetForm,
)
from django.utils.safestring import mark_safe

from .models import RecipientProfile, VolunteerProfile

User = get_user_model()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class RegisterForm(UserCreationForm):
    """Registration form with email, name, and account-type selection."""

    email = forms.EmailField(
        label="Електронна пошта",
        widget=forms.EmailInput(attrs={"placeholder": "email@example.com"}),
    )
    first_name = forms.CharField(
        label="Ім'я",
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Ім'я"}),
    )
    last_name = forms.CharField(
        label="Прізвище",
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Прізвище"}),
    )
    user_type = forms.ChoiceField(
        label="Тип акаунту",
        choices=User.UserType.choices,
        widget=forms.RadioSelect,
    )
    accept_terms = forms.BooleanField(
        label=mark_safe(
            'Я погоджуюся з <a href="/rules/" target="_blank">Правилами</a> та '
            '<a href="/privacy/" target="_blank">Політикою конфіденційності</a>'
        ),
        error_messages={"required": "Без згоди з правилами зареєструватися не можна."},
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "user_type",
            "password1",
            "password2",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "placeholder": "Ім'я користувача",
                "autocomplete": "username",
            }
        )
        self.fields["email"].widget.attrs.update({"autocomplete": "email"})
        self.fields["first_name"].widget.attrs.update({"autocomplete": "given-name"})
        self.fields["last_name"].widget.attrs.update({"autocomplete": "family-name"})
        self.fields["password1"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["password2"].widget.attrs.update({"autocomplete": "new-password"})

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Користувач з такою електронною поштою вже існує.")
        return email


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class LoginForm(AuthenticationForm):
    """Styled login form."""

    username = forms.CharField(
        label="Ім'я користувача",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ім'я користувача",
                "autofocus": True,
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Пароль",
                "autocomplete": "current-password",
            }
        ),
    )


# ---------------------------------------------------------------------------
# Profile editing
# ---------------------------------------------------------------------------


class UserProfileForm(forms.ModelForm):
    """Edit core user fields (shared by both roles)."""

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "latitude",
            "longitude",
            "date_of_birth",
            "avatar",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_of_birth"].input_formats = ["%Y-%m-%d"]
        self.fields["email"].widget.attrs.update({"autocomplete": "email"})
        self.fields["first_name"].widget.attrs.update({"autocomplete": "given-name"})
        self.fields["last_name"].widget.attrs.update({"autocomplete": "family-name"})
        self.fields["phone"].widget.attrs.update({"autocomplete": "tel"})
        self.fields["address"].widget.attrs.update({"autocomplete": "street-address"})

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and hasattr(avatar, "size"):
            max_size = 2 * 1024 * 1024  # 2 MB
            if avatar.size > max_size:
                raise forms.ValidationError("Розмір зображення не повинен перевищувати 2 МБ.")
        return avatar


class VolunteerProfileForm(forms.ModelForm):
    """Extra fields for volunteer users."""

    class Meta:
        model = VolunteerProfile
        fields = ["categories", "radius_km", "is_available", "bio"]
        widgets = {
            "categories": forms.CheckboxSelectMultiple,
            "bio": forms.Textarea(attrs={"rows": 3, "placeholder": "Розкажіть про себе..."}),
        }


class RecipientProfileForm(forms.ModelForm):
    """Extra fields for help-recipient users."""

    class Meta:
        model = RecipientProfile
        fields = ["situation_type", "emergency_contact_name", "emergency_contact_phone"]
        widgets = {
            "emergency_contact_phone": forms.TextInput(attrs={"placeholder": "+380..."}),
        }


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------


class CustomPasswordChangeForm(DjangoPasswordChangeForm):
    """Styled password-change form (inherits all Django validation)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.update({"autocomplete": "current-password"})
        self.fields["new_password1"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["new_password2"].widget.attrs.update({"autocomplete": "new-password"})


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


class SafePasswordResetForm(DjangoPasswordResetForm):
    """Demo accounts are shared by everyone, so their password cannot be reset."""

    email = forms.EmailField(
        label="Електронна пошта",
        widget=forms.EmailInput(
            attrs={"autocomplete": "email", "placeholder": "email@example.com"}
        ),
    )

    def get_users(self, email):
        return (user for user in super().get_users(email) if not user.is_demo)


class StyledSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["new_password2"].widget.attrs.update({"autocomplete": "new-password"})


class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        label="Ваш пароль",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    confirm = forms.BooleanField(label="Я розумію, що це незворотно")

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Невірний пароль.")
        return password
