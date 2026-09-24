from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeView,
)
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView

from apps.moderation.services import latest_verification, verified_organization
from apps.reviews.models import Review
from apps.reviews.services import pending_reviews, rating_summary

from . import emails
from .forms import (
    CustomPasswordChangeForm,
    LoginForm,
    RecipientProfileForm,
    RegisterForm,
    UserProfileForm,
    VolunteerProfileForm,
)
from .models import User
from .permissions import MODERATORS_GROUP, can_view_profile

# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------


class HomeView(TemplateView):
    """Landing page with platform statistics."""

    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_users"] = User.objects.count()
        context["total_volunteers"] = User.objects.filter(
            user_type=User.UserType.VOLUNTEER,
        ).count()
        context["total_recipients"] = User.objects.filter(
            user_type=User.UserType.RECIPIENT,
        ).count()
        # Local import avoids circular dependency between accounts and requests apps
        from apps.requests.models import HelpRequest

        active_requests = HelpRequest.objects.filter(status=HelpRequest.Status.ACTIVE)
        context["active_requests_count"] = active_requests.count()
        context["recent_requests"] = active_requests.select_related("category").order_by(
            "-created_at"
        )[:3]
        return context


# ---------------------------------------------------------------------------
# Live stats JSON endpoint (public — used by home page polling)
# ---------------------------------------------------------------------------


def live_stats(request):
    """JSON endpoint: live platform statistics for home page polling."""
    from apps.requests.models import HelpRequest  # local import to avoid circular

    return JsonResponse(
        {
            "total_users": User.objects.count(),
            "total_volunteers": User.objects.filter(
                user_type=User.UserType.VOLUNTEER,
            ).count(),
            "total_recipients": User.objects.filter(
                user_type=User.UserType.RECIPIENT,
            ).count(),
            "active_requests": HelpRequest.objects.filter(
                status=HelpRequest.Status.ACTIVE,
            ).count(),
        }
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class RegisterView(CreateView):
    """User registration with automatic profile creation (via signal)."""

    template_name = "accounts/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("home")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        # "Я хочу допомагати" / "Мені потрібна допомога" buttons preselect the role
        role = self.request.GET.get("role")
        return {"user_type": role} if role in User.UserType.values else {}

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend="django.contrib.auth.backends.ModelBackend")
        emails.send_confirmation(self.request, self.object)
        messages.success(
            self.request,
            f"Вітаємо, {self.object.first_name}! Ми надіслали лист на {self.object.email} — "
            "підтвердіть адресу, щоб почати допомагати або просити про допомогу.",
        )
        return response


def confirm_email(request, token):
    user = emails.confirm(token)
    if user is None:
        messages.error(
            request, "Посилання недійсне або застаріло. Надішліть лист повторно з профілю."
        )
    else:
        messages.success(request, "Email підтверджено. Дякуємо!")
    return redirect("accounts:profile" if request.user.is_authenticated else "accounts:login")


@require_POST
def resend_confirmation(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    if request.user.email_verified_at:
        messages.info(request, "Ваш email уже підтверджено.")
    elif emails.send_confirmation(request, request.user):
        messages.success(request, f"Лист надіслано на {request.user.email}.")
    else:
        messages.warning(request, "Лист уже надіслано — зачекайте пару хвилин і перевірте пошту.")
    return redirect("accounts:profile")


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------


class CustomLoginView(LoginView):
    """Login page with styled form."""

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["demo_mode"] = settings.DEMO_MODE
        context["demo_roles"] = [
            ("volunteer", "Я волонтер", "bi-hand-thumbs-up"),
            ("recipient", "Мені потрібна допомога", "bi-heart"),
            ("moderator", "Модератор", "bi-shield-check"),
        ]
        return context

    def form_valid(self, form):
        messages.success(self.request, f"З поверненням, {form.get_user().first_name}!")
        return super().form_valid(form)


class CustomLogoutView(LogoutView):
    """Logout and redirect to home."""

    next_page = reverse_lazy("home")

    def dispatch(self, request, *args, **kwargs):
        messages.info(request, "Ви вийшли з акаунту.")
        return super().dispatch(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Profile — view
# ---------------------------------------------------------------------------


class ProfileView(LoginRequiredMixin, DetailView):
    """Display current user's profile with stats and reviews."""

    model = User
    template_name = "accounts/profile.html"
    context_object_name = "profile_user"

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object
        context.update(_profile_stats(user))
        context["pending_reviews"] = pending_reviews(user)
        context["latest_verification"] = latest_verification(user)
        context["verified_organization"] = verified_organization(user)
        return context


def _profile_stats(user):
    """Rating and activity numbers shared by the own and the public profile."""
    from apps.requests.models import HelpRequest, Response

    summary = rating_summary(user)
    stats = {
        "rating": summary,
        "avg_rating": summary.average,
        "review_count": summary.count,
        "reviews": Review.objects.published()
        .filter(target=user)
        .select_related("author", "help_request")[:10],
    }
    if user.is_volunteer:
        stats["volunteer_profile"] = getattr(user, "volunteer_profile", None)
        stats["responses_count"] = user.volunteer_responses.count()
        stats["accepted_count"] = user.volunteer_responses.filter(
            status=Response.Status.ACCEPTED
        ).count()
        stats["helped_count"] = user.volunteer_responses.filter(
            status=Response.Status.ACCEPTED, help_request__status=HelpRequest.Status.COMPLETED
        ).count()
    elif user.is_recipient:
        stats["recipient_profile"] = getattr(user, "recipient_profile", None)
        stats["requests_count"] = user.help_requests.count()
        stats["completed_count"] = user.help_requests.filter(
            status=HelpRequest.Status.COMPLETED
        ).count()
    return stats


class PublicProfileView(LoginRequiredMixin, DetailView):
    """
    Another user's profile, visible only to people they deal with
    (see apps.accounts.permissions). Contacts and address are never shown.
    """

    model = User
    template_name = "accounts/public_profile.html"
    context_object_name = "profile_user"

    def get_object(self, queryset=None):
        user = super().get_object(queryset)
        if user.pk == self.request.user.pk:
            return user
        if not can_view_profile(self.request.user, user):
            raise Http404
        return user

    def get(self, request, *args, **kwargs):
        if kwargs["pk"] == request.user.pk:
            return redirect("accounts:profile")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_profile_stats(self.object))
        context["verified_organization"] = verified_organization(self.object)
        return context


# ---------------------------------------------------------------------------
# Profile — edit
# ---------------------------------------------------------------------------


class ProfileEditView(LoginRequiredMixin, UpdateView):
    """Edit current user's profile (core fields + role-specific fields)."""

    model = User
    form_class = UserProfileForm
    template_name = "accounts/profile_edit.html"
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if "role_form" not in context:
            if user.is_volunteer:
                profile = getattr(user, "volunteer_profile", None)
                context["role_form"] = VolunteerProfileForm(
                    instance=profile,
                    prefix="role",
                )
            elif user.is_recipient:
                profile = getattr(user, "recipient_profile", None)
                context["role_form"] = RecipientProfileForm(
                    instance=profile,
                    prefix="role",
                )

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()

        # Build role-specific form
        user = request.user
        role_form = None
        if user.is_volunteer:
            role_form = VolunteerProfileForm(
                request.POST,
                instance=getattr(user, "volunteer_profile", None),
                prefix="role",
            )
        elif user.is_recipient:
            role_form = RecipientProfileForm(
                request.POST,
                instance=getattr(user, "recipient_profile", None),
                prefix="role",
            )

        if form.is_valid() and (role_form is None or role_form.is_valid()):
            form.save()
            if role_form:
                role_form.save()
            messages.success(request, "Профіль оновлено.")
            return redirect(self.success_url)

        # Re-render with errors
        context = self.get_context_data(form=form)
        if role_form:
            context["role_form"] = role_form
        return self.render_to_response(context)


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------


class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """Change password with styled form."""

    template_name = "accounts/password_change.html"
    form_class = CustomPasswordChangeForm
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        messages.success(self.request, "Пароль успішно змінено.")
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Demo login (portfolio demo; only when settings.DEMO_MODE is on)
# ---------------------------------------------------------------------------

# Demo accounts never get is_staff/is_superuser: anyone on the internet can use them
DEMO_ROLES = {
    "volunteer": {"user_type": User.UserType.VOLUNTEER},
    "recipient": {"user_type": User.UserType.RECIPIENT},
    "moderator": {"groups__name": MODERATORS_GROUP},
}


def _other_demo_roles(role):
    """Moderator demo user is also a volunteer; keep role buttons distinct."""
    if role == "moderator":
        return []
    return User.objects.filter(groups__name=MODERATORS_GROUP).values("pk")


@require_POST
def demo_login(request, role):
    """Log in as the demo account of a role with one click — no password involved."""
    if not settings.DEMO_MODE or role not in DEMO_ROLES:
        raise Http404
    user = (
        User.objects.filter(
            is_demo=True, is_active=True, is_staff=False, is_superuser=False, **DEMO_ROLES[role]
        )
        .exclude(pk__in=_other_demo_roles(role))
        .first()
    )
    if user is None:
        messages.error(request, "Демо-акаунт ще не створено.")
        return redirect("accounts:login")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.info(request, f"Ви увійшли як демо-користувач: {user.get_full_name()}.")
    return redirect("home")
