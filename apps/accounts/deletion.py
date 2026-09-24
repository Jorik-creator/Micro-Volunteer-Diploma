"""
Self-service account deletion (ROADMAP stage 8, privacy by design).

The account row is kept so that foreign keys (reviews, finished requests,
conversations) stay consistent, but everything that identifies the person is
erased: names, contacts, addresses, photos, message texts, verification
answers and notifications. Reviews they wrote remain, signed as
"Видалений користувач", so other people's ratings do not change.
"""

from django.db import transaction
from django.db.models import Q

from apps.conversations.models import Message
from apps.moderation.models import Report, VerificationRequest
from apps.notifications.models import Notification
from apps.requests import services as request_services
from apps.requests.models import HelpRequest, Response

REMOVED_TEXT = "Видалено на прохання користувача."
ANONYMOUS = "Видалений користувач"


class DeletionError(Exception):
    pass


def _delete_file(field):
    if field:
        field.delete(save=False)


def delete_account(user):
    if user.is_demo:
        raise DeletionError("Демо-акаунт видалити не можна.")
    if user.is_superuser:
        raise DeletionError("Акаунт адміністратора видаляється вручну.")

    with transaction.atomic():
        full_name = user.get_full_name().strip()
        names = [name for name in (full_name, user.short_name.strip()) if name]
        request_services.close_open_work_of(user, "Користувач видалив акаунт.")
        # Other people's notifications mention the user by name: the full name in
        # older ones, the short "Анна К." form in newer ones. The short form is
        # common, so it is only replaced in notifications about shared requests.
        mentions = Q(related_request__recipient=user) | Q(
            related_request__responses__volunteer=user
        )
        if full_name:
            mentions |= Q(title__contains=full_name) | Q(message__contains=full_name)
        for notification in Notification.objects.filter(mentions).exclude(user=user).distinct():
            title, message = notification.title, notification.message
            for name in names:
                title = title.replace(name, ANONYMOUS)
                message = message.replace(name, ANONYMOUS)
            if (title, message) != (notification.title, notification.message):
                notification.title, notification.message = title, message
                notification.save(update_fields=["title", "message"])
        Report.objects.filter(reporter=user).update(comment="")
        for help_request in HelpRequest.objects.filter(recipient=user):
            _delete_file(help_request.photo)
            help_request.address = ""
            help_request.latitude = help_request.longitude = None
            help_request.beneficiary_name = help_request.beneficiary_phone = ""
            help_request.description = REMOVED_TEXT
            help_request.title = "Запит видаленого користувача"
            help_request.save(
                update_fields=[
                    "title",
                    "photo",
                    "address",
                    "latitude",
                    "longitude",
                    "beneficiary_name",
                    "beneficiary_phone",
                    "description",
                ]
            )
        Response.objects.filter(volunteer=user).update(message="", status_reason="")
        Message.objects.filter(sender=user).update(body=REMOVED_TEXT)
        VerificationRequest.objects.filter(user=user).delete()
        Notification.objects.filter(user=user).delete()

        profile = getattr(user, "volunteer_profile", None)
        if profile:
            profile.bio = ""
            profile.is_available = False
            profile.save(update_fields=["bio", "is_available"])
            profile.categories.clear()
        profile = getattr(user, "recipient_profile", None)
        if profile:
            profile.situation_type = ""
            profile.emergency_contact_name = profile.emergency_contact_phone = ""
            profile.save()

        _delete_file(user.avatar)
        user.username = f"deleted-{user.pk}"
        user.email = f"deleted-{user.pk}@deleted.invalid"
        user.first_name = "Видалений"
        user.last_name = "користувач"
        user.phone = user.address = ""
        user.latitude = user.longitude = None
        user.date_of_birth = None
        user.is_active = False
        user.is_verified = False
        user.email_verified_at = None
        user.set_unusable_password()
        user.save()
