from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm as DjangoPasswordChangeForm,
    UserCreationForm,
)

from .models import RecipientProfile, VolunteerProfile

User = get_user_model()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterForm(UserCreationForm):
    """Registration form with email, name, and account-type selection."""

    email = forms.EmailField(
        label='Електронна пошта',
        widget=forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
    )
    first_name = forms.CharField(
        label="Ім'я",
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': "Ім'я"}),
    )
    last_name = forms.CharField(
        label='Прізвище',
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Прізвище'}),
    )
    user_type = forms.ChoiceField(
        label='Тип акаунту',
        choices=User.UserType.choices,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = User
        fields = [
            'username',
            'email',
            'first_name',
            'last_name',
            'user_type',
            'password1',
            'password2',
        ]

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Користувач з такою електронною поштою вже існує.')
        return email


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginForm(AuthenticationForm):
    """Styled login form."""

    username = forms.CharField(
        label="Ім'я користувача",
        widget=forms.TextInput(attrs={'placeholder': "Ім'я користувача", 'autofocus': True}),
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'placeholder': 'Пароль'}),
    )


# ---------------------------------------------------------------------------
# Profile editing
# ---------------------------------------------------------------------------

class UserProfileForm(forms.ModelForm):
    """Edit core user fields (shared by both roles)."""

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'email',
            'phone',
            'address',
            'latitude',
            'longitude',
            'date_of_birth',
            'avatar',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d',
            ),
            'latitude': forms.NumberInput(attrs={'step': '0.000001', 'placeholder': '50.4501'}),
            'longitude': forms.NumberInput(attrs={'step': '0.000001', 'placeholder': '30.5234'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_of_birth'].input_formats = ['%Y-%m-%d']

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and hasattr(avatar, 'size'):
            max_size = 2 * 1024 * 1024  # 2 MB
            if avatar.size > max_size:
                raise forms.ValidationError('Розмір зображення не повинен перевищувати 2 МБ.')
        return avatar


class VolunteerProfileForm(forms.ModelForm):
    """Extra fields for volunteer users."""

    class Meta:
        model = VolunteerProfile
        fields = ['categories', 'radius_km', 'is_available', 'bio']
        widgets = {
            'categories': forms.CheckboxSelectMultiple,
            'bio': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Розкажіть про себе...'}),
        }


class RecipientProfileForm(forms.ModelForm):
    """Extra fields for help-recipient users."""

    class Meta:
        model = RecipientProfile
        fields = ['situation_type', 'emergency_contact_name', 'emergency_contact_phone']
        widgets = {
            'emergency_contact_phone': forms.TextInput(attrs={'placeholder': '+380...'}),
        }


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------

class CustomPasswordChangeForm(DjangoPasswordChangeForm):
    """Styled password-change form (inherits all Django validation)."""
    pass
