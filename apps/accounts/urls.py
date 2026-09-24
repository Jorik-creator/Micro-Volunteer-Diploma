from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import SafePasswordResetForm, StyledSetPasswordForm

app_name = "accounts"

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("confirm-email/resend/", views.resend_confirmation, name="resend-confirmation"),
    path("confirm-email/<str:token>/", views.confirm_email, name="confirm-email"),
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("demo/<slug:role>/", views.demo_login, name="demo-login"),
    path("logout/", views.CustomLogoutView.as_view(), name="logout"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("users/<int:pk>/", views.PublicProfileView.as_view(), name="public-profile"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="profile-edit"),
    path("password-change/", views.CustomPasswordChangeView.as_view(), name="password-change"),
    # Password reset (standard Django flow with our templates)
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=SafePasswordResetForm,
            template_name="accounts/password_reset_form.html",
            email_template_name="emails/password_reset.txt",
            html_email_template_name="emails/password_reset.html",
            subject_template_name="emails/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password-reset-done"),
        ),
        name="password-reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password-reset-done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            form_class=StyledSetPasswordForm,
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password-reset-complete"),
        ),
        name="password-reset-confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password-reset-complete",
    ),
]
