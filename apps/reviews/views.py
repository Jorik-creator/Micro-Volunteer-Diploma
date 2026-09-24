"""
Views for the reviews app.

CreateReviewView — a participant of a completed request rates the other side.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import FormView

from apps.accounts.models import User
from apps.requests.models import HelpRequest

from . import services
from .forms import ReviewForm


class CreateReviewView(LoginRequiredMixin, FormView):
    form_class = ReviewForm
    template_name = "reviews/review_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.help_request = get_object_or_404(HelpRequest, pk=kwargs["request_pk"])
        self.target = get_object_or_404(User, pk=kwargs["target_pk"])
        error = services.review_error(request.user, self.help_request, self.target)
        if error:
            messages.error(request, error)
            return redirect("requests:detail", pk=self.help_request.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "target": self.target}

    def form_valid(self, form):
        try:
            services.submit_review(
                self.request.user,
                self.help_request,
                self.target,
                form.cleaned_data["rating"],
                form.cleaned_data["tags"],
                form.cleaned_data["comment"],
            )
        except services.ReviewError as error:
            messages.error(self.request, str(error))
        else:
            messages.success(
                self.request,
                "Дякуємо за оцінку! Вона стане видимою, коли інша сторона теж залишить свою "
                "(або через 14 днів).",
            )
        return redirect("requests:detail", pk=self.help_request.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["help_request"] = self.help_request
        context["target"] = self.target
        context["deadline"] = services.review_deadline(self.help_request)
        return context
