"""
Who may see whose profile (ROADMAP: "Люди").

Profiles are not public. A recipient deciding whom to accept may open the
profile of any volunteer who responded to their request; a volunteer may see
the (minimal) profile of a recipient whose request they responded to.
"""

from apps.requests.models import Response

MODERATORS_GROUP = "Модератори"


def is_moderator(user):
    """Moderators work in the on-site queue; they do not need Django admin (is_staff)."""
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name=MODERATORS_GROUP).exists()
    )


def can_view_profile(viewer, user):
    if not viewer.is_authenticated:
        return False
    if viewer.pk == user.pk or is_moderator(viewer):
        return True
    if user.is_volunteer:
        return Response.objects.filter(volunteer=user, help_request__recipient=viewer).exists()
    return Response.objects.filter(volunteer=viewer, help_request__recipient=user).exists()
