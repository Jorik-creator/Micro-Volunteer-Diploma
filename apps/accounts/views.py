from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeView,
)
from django.db.models import Avg, Count
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, UpdateView, TemplateView

from .forms import (
    CustomPasswordChangeForm,
    LoginForm,
    RecipientProfileForm,
    RegisterForm,
    UserProfileForm,
    VolunteerProfileForm,
)
from .models import User


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------

class HomeView(TemplateView):
    """Landing page with platform statistics."""

    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_users'] = User.objects.count()
        context['total_volunteers'] = User.objects.filter(
            user_type=User.UserType.VOLUNTEER,
        ).count()
        context['total_recipients'] = User.objects.filter(
            user_type=User.UserType.RECIPIENT,
        ).count()
        # Local import avoids circular dependency between accounts and requests apps
        from apps.requests.models import HelpRequest
        context['recent_requests'] = (
            HelpRequest.objects.filter(status=HelpRequest.Status.ACTIVE)
            .select_related('category')
            .order_by('-created_at')[:3]
        )
        return context


# ---------------------------------------------------------------------------
# Live stats JSON endpoint (public — used by home page polling)
# ---------------------------------------------------------------------------


def live_stats(request):
    """JSON endpoint: live platform statistics for home page polling."""
    from apps.requests.models import HelpRequest  # local import to avoid circular
    return JsonResponse({
        "total_users": User.objects.count(),
        "total_volunteers": User.objects.filter(user_type=User.UserType.VOLUNTEER).count(),
        "total_recipients": User.objects.filter(user_type=User.UserType.RECIPIENT).count(),
        "active_requests": HelpRequest.objects.filter(status=HelpRequest.Status.ACTIVE).count(),
    })


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterView(CreateView):
    """User registration with automatic profile creation (via signal)."""

    template_name = 'accounts/register.html'
    form_class = RegisterForm
    success_url = reverse_lazy('home')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(
            self.request,
            f'Вітаємо, {self.object.first_name}! Ваш акаунт створено.',
        )
        return response


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

class CustomLoginView(LoginView):
    """Login page with styled form."""

    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, f'З поверненням, {form.get_user().first_name}!')
        return super().form_valid(form)


class CustomLogoutView(LogoutView):
    """Logout and redirect to home."""

    next_page = reverse_lazy('home')

    def dispatch(self, request, *args, **kwargs):
        messages.info(request, 'Ви вийшли з акаунту.')
        return super().dispatch(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Profile — view
# ---------------------------------------------------------------------------

class ProfileView(LoginRequiredMixin, DetailView):
    """Display current user's profile with stats and reviews."""

    model = User
    template_name = 'accounts/profile.html'
    context_object_name = 'profile_user'

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()

        # Rating stats
        reviews = user.reviews_received.all()
        context['reviews'] = reviews.order_by('-created_at')[:5]
        context['review_count'] = reviews.count()
        agg = reviews.aggregate(avg=Avg('rating'))
        context['avg_rating'] = round(agg['avg'], 1) if agg['avg'] else None

        # Role-specific stats
        if user.is_volunteer:
            context['volunteer_profile'] = getattr(user, 'volunteer_profile', None)
            context['responses_count'] = user.volunteer_responses.count()
            context['accepted_count'] = user.volunteer_responses.filter(status='accepted').count()
        elif user.is_recipient:
            context['recipient_profile'] = getattr(user, 'recipient_profile', None)
            context['requests_count'] = user.help_requests.count()
            context['completed_count'] = user.help_requests.filter(status='completed').count()

        return context


# ---------------------------------------------------------------------------
# Profile — edit
# ---------------------------------------------------------------------------

class ProfileEditView(LoginRequiredMixin, UpdateView):
    """Edit current user's profile (core fields + role-specific fields)."""

    model = User
    form_class = UserProfileForm
    template_name = 'accounts/profile_edit.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if 'role_form' not in context:
            if user.is_volunteer:
                profile = getattr(user, 'volunteer_profile', None)
                context['role_form'] = VolunteerProfileForm(
                    instance=profile, prefix='role',
                )
            elif user.is_recipient:
                profile = getattr(user, 'recipient_profile', None)
                context['role_form'] = RecipientProfileForm(
                    instance=profile, prefix='role',
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
                instance=getattr(user, 'volunteer_profile', None),
                prefix='role',
            )
        elif user.is_recipient:
            role_form = RecipientProfileForm(
                request.POST,
                instance=getattr(user, 'recipient_profile', None),
                prefix='role',
            )

        if form.is_valid() and (role_form is None or role_form.is_valid()):
            form.save()
            if role_form:
                role_form.save()
            messages.success(request, 'Профіль оновлено.')
            return redirect(self.success_url)

        # Re-render with errors
        context = self.get_context_data(form=form)
        if role_form:
            context['role_form'] = role_form
        return self.render_to_response(context)


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------

class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """Change password with styled form."""

    template_name = 'accounts/password_change.html'
    form_class = CustomPasswordChangeForm
    success_url = reverse_lazy('accounts:profile')

    def form_valid(self, form):
        messages.success(self.request, 'Пароль успішно змінено.')
        return super().form_valid(form)
