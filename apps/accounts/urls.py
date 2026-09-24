from django.urls import path

from . import views

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
    path("stats/", views.live_stats, name="live-stats"),
]
