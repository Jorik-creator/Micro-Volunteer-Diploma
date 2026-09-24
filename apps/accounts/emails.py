"""
Email confirmation (trust level L1).

The link carries a signed token with the user id and the email it was sent
to, so changing the email invalidates older links. No database table needed.
"""

from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import User

SALT = "accounts.email-confirmation"
MAX_AGE = 60 * 60 * 24 * 3  # three days
RESEND_COOLDOWN = 60 * 2


def make_token(user):
    return signing.dumps({"u": user.pk, "e": user.email}, salt=SALT)


def send_confirmation(request, user):
    """Send (or resend) the confirmation link. Returns False when throttled."""
    throttle_key = f"email-confirm-sent:{user.pk}"
    if not cache.add(throttle_key, True, RESEND_COOLDOWN):
        return False
    link = request.build_absolute_uri(reverse("accounts:confirm-email", args=[make_token(user)]))
    context = {"user": user, "link": link, "days": MAX_AGE // 86400}
    send_mail(
        subject="Підтвердіть email — MicroVolunteer",
        message=render_to_string("emails/confirm_email.txt", context),
        from_email=None,
        recipient_list=[user.email],
        html_message=render_to_string("emails/confirm_email.html", context),
    )
    return True


def confirm(token):
    """Mark the email confirmed; returns the user or None for a bad/expired link."""
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        return None
    user = User.objects.filter(pk=data.get("u"), email=data.get("e")).first()
    if user and user.email_verified_at is None:
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
    return user
