from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeView,
)
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, FormView, TemplateView, UpdateView

from apps.moderation.services import latest_verification, verified_organization
from apps.reviews.models import Review
from apps.reviews.services import pending_reviews, rating_summary

from . import emails
from .deletion import DeletionError, delete_account
from .forms import (
    CustomPasswordChangeForm,
    DeleteAccountForm,
    LoginForm,
    RecipientProfileForm,
    RegisterForm,
    UserProfileForm,
    VolunteerProfileForm,
)
from .models import User
from .permissions import MODERATORS_GROUP, can_view_profile, is_moderator

# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------


class HomeView(TemplateView):
    """Landing page: role entry points, real platform numbers, newest requests."""

    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Local import avoids circular dependency between accounts and requests apps
        from apps.requests.models import HelpRequest

        active = HelpRequest.objects.filter(status=HelpRequest.Status.ACTIVE)
        context["active_requests_count"] = active.count()
        context["completed_requests_count"] = HelpRequest.objects.filter(
            status=HelpRequest.Status.COMPLETED
        ).count()
        context["verified_volunteers_count"] = User.objects.filter(
            user_type=User.UserType.VOLUNTEER, is_verified=True, is_active=True
        ).count()
        recent = active.select_related("category").order_by("-published_at")
        user = self.request.user
        if user.is_authenticated and user.is_recipient:
            recent = recent.exclude(recipient=user)
        context["recent_requests"] = recent[:6]
        context["action_items"] = action_items(user) if user.is_authenticated else []
        return context


MAX_ACTION_ITEMS = 4


def _item(icon, title, text, url, tone=""):
    return {"icon": icon, "title": title, "text": text, "url": url, "tone": tone}


def _single_or_list(requests, list_url):
    """The request page when there is exactly one, otherwise the list."""
    return reverse("requests:detail", args=[requests[0].pk]) if len(requests) == 1 else list_url


def action_items(user, now=None):
    """
    What the signed-in user should do next, most pressing first (at most
    MAX_ACTION_ITEMS). Each item: {icon, title, text, url, tone}, where tone is
    "" | "warning" | "success". Empty when there is nothing to do.
    """
    now = now or timezone.now()
    items = _moderator_items(user)
    if not user.email_verified_at:
        items.append(
            _item(
                "bi-envelope-exclamation",
                "Підтвердіть email",
                "Без цього не можна публікувати запити чи відгукуватися на них.",
                reverse("accounts:profile"),
                "warning",
            )
        )
    if user.is_recipient:
        items += _recipient_items(user)
    elif user.is_volunteer:
        items += _volunteer_items(user, now)
    items += _review_items(user, now)
    return items[:MAX_ACTION_ITEMS]


def _moderator_items(user):
    if not is_moderator(user):
        return []
    from apps.moderation.models import Report, VerificationRequest
    from apps.requests.models import HelpRequest

    queue = reverse("moderation:queue")
    counts = [
        (
            VerificationRequest.objects.filter(status=VerificationRequest.Status.PENDING).count(),
            "bi-patch-check",
            "Заявки на перевірку",
            "verification",
            "",
        ),
        (
            HelpRequest.objects.filter(status=HelpRequest.Status.PENDING_MODERATION).count(),
            "bi-file-earmark-text",
            "Запити на модерації",
            "requests",
            "",
        ),
        (
            Report.objects.filter(status=Report.Status.OPEN).count(),
            "bi-flag",
            "Скарги",
            "reports",
            "warning",
        ),
    ]
    return [
        _item(
            icon,
            f"{title}: {count}",
            "Черга модерації чекає на розгляд.",
            f"{queue}?tab={tab}",
            tone,
        )
        for count, icon, title, tab, tone in counts
        if count
    ]


def _recipient_items(user):
    from apps.requests.models import HelpRequest, Response

    S = HelpRequest.Status
    mine = list(
        HelpRequest.objects.filter(
            recipient=user,
            status__in=[S.AWAITING_CONFIRMATION, S.ACTIVE, S.REJECTED, S.DRAFT],
        )
        .annotate(pending=Count("responses", filter=Q(responses__status=Response.Status.PENDING)))
        .order_by("-status_changed_at")
    )
    my_requests = reverse("requests:my-requests")
    items = []

    awaiting = [hr for hr in mine if hr.status == S.AWAITING_CONFIRMATION]
    if awaiting:
        items.append(
            _item(
                "bi-check2-circle",
                "Підтвердіть виконання",
                f"«{awaiting[0].title}» — волонтери позначили допомогу виконаною."
                if len(awaiting) == 1
                else f"Запитів, де волонтери позначили допомогу виконаною: {len(awaiting)}.",
                _single_or_list(awaiting, my_requests),
                "warning",
            )
        )

    with_responses = [hr for hr in mine if hr.status == S.ACTIVE and hr.pending]
    if with_responses:
        items.append(
            _item(
                "bi-people",
                f"Нові відгуки волонтерів: {sum(hr.pending for hr in with_responses)}",
                f"«{with_responses[0].title}» — перегляньте й оберіть волонтера."
                if len(with_responses) == 1
                else "Перегляньте відгуки й оберіть волонтерів.",
                _single_or_list(with_responses, my_requests),
            )
        )

    rejected = [hr for hr in mine if hr.status == S.REJECTED]
    if rejected:
        items.append(
            _item(
                "bi-pencil",
                "Виправте запит",
                "Модератор повернув запит — відредагуйте його, і він піде на повторну перевірку.",
                _single_or_list(rejected, my_requests),
                "warning",
            )
        )

    drafts = [hr for hr in mine if hr.status == S.DRAFT]
    if drafts:
        items.append(
            _item(
                "bi-pencil",
                "Опублікуйте чернетку",
                f"«{drafts[0].title}» ще не бачать волонтери."
                if len(drafts) == 1
                else f"Неопублікованих чернеток: {len(drafts)}.",
                _single_or_list(drafts, my_requests),
            )
        )
    return items


def _volunteer_items(user, now):
    from apps.conversations.services import unread_count
    from apps.moderation.services import application_error
    from apps.requests.models import HelpRequest, Response

    items = []
    to_mark = [
        response.help_request
        for response in Response.objects.filter(
            volunteer=user,
            status=Response.Status.ACCEPTED,
            done_at__isnull=True,
            help_request__status=HelpRequest.Status.IN_PROGRESS,
        )
        .select_related("help_request")
        .order_by("help_request__needed_date")
    ]
    if to_mark:
        first = to_mark[0]
        items.append(
            _item(
                "bi-check2-circle",
                "Позначте виконання після допомоги",
                f"«{first.title}», {timezone.localtime(first.needed_date):%d.%m о %H:%M}."
                if len(to_mark) == 1
                else f"Запитів у процесі: {len(to_mark)}. Найближчий — «{first.title}».",
                _single_or_list(to_mark, reverse("requests:my-responses")),
                # Once the help time has come, this is the next thing to do
                "warning" if first.needed_date <= now else "",
            )
        )

    unread = unread_count(user)
    if unread:
        items.append(
            _item(
                "bi-chat-dots",
                f"Нові повідомлення: {unread}",
                "Відкрийте розмови, щоб відповісти.",
                reverse("conversations:list"),
            )
        )

    if user.email_verified_at and application_error(user) is None:
        items.append(
            _item(
                "bi-patch-check",
                "Пройдіть перевірку",
                "Перевіреним волонтерам доступні візити додому.",
                reverse("moderation:apply"),
            )
        )
    return items


def _review_items(user, now):
    pending = pending_reviews(user, now)
    if not pending:
        return []
    help_request, target = pending[0]
    if len(pending) == 1:
        text = f"Як пройшла допомога із запитом «{help_request.title}»?"
        url = reverse("reviews:review-create", args=[help_request.pk, target.pk])
    else:
        text = f"Оцінок, які ви ще можете залишити: {len(pending)}."
        url = reverse("accounts:profile")
    return [_item("bi-star", "Залиште оцінку", text, url, "success")]


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
        if settings.DEMO_MODE:
            # The public demo is reset daily and its moderator is open to everyone,
            # so real people must not register there.
            messages.info(request, "Це демонстраційна версія — скористайтеся кнопками демо-входу.")
            return redirect("accounts:login")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        # "Я хочу допомагати" / "Мені потрібна допомога" buttons preselect the role
        role = self.request.GET.get("role")
        return {"user_type": role} if role in User.UserType.values else {}

    def form_valid(self, form):
        form.instance.terms_accepted_at = timezone.now()
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

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_demo:
            # Shared demo accounts must not be hijacked by changing the email
            form.fields["email"].disabled = True
        return form

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
            email_changed = "email" in form.changed_data
            user = form.save(commit=False)
            if email_changed:
                user.email_verified_at = None
            user.save()
            if role_form:
                role_form.save()
            messages.success(request, "Профіль оновлено.")
            if email_changed:
                emails.send_confirmation(request, user)
                messages.info(
                    request, f"Підтвердіть нову адресу — ми надіслали лист на {user.email}."
                )
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

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_demo:
            messages.info(request, "Пароль демо-акаунта змінити не можна.")
            return redirect("accounts:profile")
        return super().dispatch(request, *args, **kwargs)

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


# ---------------------------------------------------------------------------
# Account deletion (privacy by design)
# ---------------------------------------------------------------------------


class DeleteAccountView(LoginRequiredMixin, FormView):
    template_name = "accounts/delete_account.html"
    form_class = DeleteAccountForm

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def form_valid(self, form):
        user = self.request.user
        try:
            delete_account(user)
        except DeletionError as error:
            messages.error(self.request, str(error))
            return redirect("accounts:profile")
        logout(self.request)
        messages.success(self.request, "Акаунт видалено. Дякуємо, що були з нами.")
        return redirect("home")
