"""
UI vocabulary of the "Solid Blue" design (docs/DESIGN.md): statuses, urgency,
categories, formats and notification types are shown as icon + text, never
as pill stickers. Templates use these tags so every page says it the same way.

    {% load mv_ui %}
    {% request_status help_request %}      {% response_status response %}
    {% urgency help_request %}             {% category_icon category %}
    {% format_icon help_request %}         {% avatar user 56 %}
    {% notification_tile notification %}   {% nav_class 'requests:list' exact=True %}
"""

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# status value -> (icon, tone, label override)
REQUEST_STATUS = {
    "draft": ("bi-pencil", "muted", None),
    "pending_moderation": ("bi-hourglass-split", "warning", None),
    "rejected": ("bi-x-octagon", "danger", None),
    "active": ("bi-circle", "blue", "Шукає волонтерів"),
    "in_progress": ("bi-circle-half", "navy", None),
    "awaiting_confirmation": ("bi-clock-history", "warning", None),
    "completed": ("bi-check-circle-fill", "success", None),
    "cancelled": ("bi-x-circle", "muted", None),
    "expired": ("bi-calendar-x", "muted", None),
}

RESPONSE_STATUS = {
    "pending": ("bi-hourglass-split", "warning", "Очікує рішення"),
    "accepted": ("bi-check-circle-fill", "success", None),
    "rejected": ("bi-x-circle", "danger", None),
    "withdrawn": ("bi-box-arrow-left", "muted", None),
    "removed": ("bi-person-dash", "muted", None),
    "closed": ("bi-lock", "muted", None),
}

URGENCY = {
    "low": "bi-reception-1",
    "medium": "bi-reception-2",
    "high": "bi-reception-3",
    "critical": "bi-reception-4",
}

FORMAT_ICON = {
    "home_visit": "bi-house-door",
    "doorstep": "bi-door-closed",
    "public_place": "bi-signpost-2",
    "remote": "bi-telephone",
}

# Bootstrap Icons has no paw; category icon "paw" renders this SVG
PAW_SVG = (
    '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
    '<ellipse cx="3.2" cy="6.3" rx="1.6" ry="2.1"/><ellipse cx="6.1" cy="3.4" rx="1.6" ry="2.2"/>'
    '<ellipse cx="9.9" cy="3.4" rx="1.6" ry="2.2"/><ellipse cx="12.8" cy="6.3" rx="1.6" ry="2.1"/>'
    '<path d="M8 7.2c-2.2 0-4.3 2.6-4.3 4.7 0 1.4 1 2.1 2.2 2.1.8 0 1.4-.4 2.1-.4s1.3.4 2.1.4c1.2 0 '
    '2.2-.7 2.2-2.1 0-2.1-2.1-4.7-4.3-4.7z"/></svg>'
)

NOTIFICATION = {
    "new_response": ("bi-chat-left-dots", ""),
    "request_accepted": ("bi-check-circle-fill", "success"),
    "request_rejected": ("bi-x-circle", "muted"),
    "response_closed": ("bi-lock", "muted"),
    "volunteer_withdrew": ("bi-box-arrow-left", "warning"),
    "volunteer_removed": ("bi-person-dash", "warning"),
    "marked_done": ("bi-check2-circle", "success"),
    "completion_disputed": ("bi-exclamation-diamond", "warning"),
    "new_nearby_request": ("bi-geo-alt", ""),
    "request_completed": ("bi-check-circle-fill", "success"),
    "request_cancelled": ("bi-x-circle", "muted"),
    "request_expired": ("bi-calendar-x", "muted"),
    "reminder": ("bi-alarm", "warning"),
    "new_review": ("bi-star-fill", ""),
    "review_reminder": ("bi-star", ""),
    "request_approved": ("bi-shield-check", "success"),
    "request_moderated": ("bi-shield-x", "danger"),
    "verification": ("bi-patch-check", ""),
    "report_resolved": ("bi-flag", ""),
    "new_message": ("bi-chat-dots", ""),
}


def _status(icon, tone, label):
    return format_html(
        '<span class="mv-status mv-status--{}"><i class="bi {}" aria-hidden="true"></i>{}</span>',
        tone,
        icon,
        label,
    )


@register.simple_tag
def request_status(help_request):
    icon, tone, label = REQUEST_STATUS.get(help_request.status, ("bi-circle", "muted", None))
    return _status(icon, tone, label or help_request.get_status_display())


@register.simple_tag
def response_status(response):
    icon, tone, label = RESPONSE_STATUS.get(response.status, ("bi-circle", "muted", None))
    return _status(icon, tone, label or response.get_status_display())


@register.simple_tag
def urgency(help_request, label=True):
    icon = URGENCY.get(help_request.urgency, "bi-reception-2")
    text = f"Терміновість: {help_request.get_urgency_display().lower()}" if label else ""
    return format_html(
        '<span class="mv-urg mv-urg--{}"><i class="bi {}" aria-hidden="true"></i>{}</span>',
        help_request.urgency,
        icon,
        text,
    )


@register.simple_tag
def urgency_icon(help_request):
    return format_html(
        '<i class="bi {}" aria-hidden="true"></i>',
        URGENCY.get(help_request.urgency, "bi-reception-2"),
    )


@register.simple_tag
def category_icon(category):
    icon = getattr(category, "icon", "") or "bi-three-dots"
    if icon == "paw":
        return mark_safe(PAW_SVG)
    if not icon.startswith("bi-"):
        icon = "bi-" + icon
    return format_html('<i class="bi {}" aria-hidden="true"></i>', icon)


@register.simple_tag
def format_icon(help_request):
    return format_html(
        '<i class="bi {}" aria-hidden="true"></i>',
        FORMAT_ICON.get(help_request.help_format, "bi-geo-alt"),
    )


@register.simple_tag
def avatar(user, size=40, badge=True):
    """Photo or navy initials; a small blue check for verified users."""
    initials = ((user.first_name[:1] or user.username[:1]) + user.last_name[:1]).upper()
    size_class = "" if int(size) == 40 else f" mv-avatar--{int(size)}"
    avatar_file = getattr(user, "avatar", None)
    inner = format_html('<img src="{}" alt="">', avatar_file.url) if avatar_file else initials
    check = (
        mark_safe(
            '<span class="mv-avatar__badge" title="Перевірений">'
            '<i class="bi bi-patch-check-fill" aria-hidden="true"></i></span>'
        )
        if badge and getattr(user, "is_verified", False)
        else ""
    )
    return format_html(
        '<span class="mv-avatar{}" aria-hidden="true">{}{}</span>', size_class, inner, check
    )


@register.simple_tag
def notification_tile(notification):
    icon, tone = NOTIFICATION.get(notification.type, ("bi-bell", ""))
    tone_class = f" mv-tile--{tone}" if tone else ""
    return format_html(
        '<span class="mv-tile{}" aria-hidden="true"><i class="bi {}"></i></span>', tone_class, icon
    )


@register.simple_tag(takes_context=True)
def nav_class(context, url_name, exact=False):
    """'nav-link is-active' when the current page belongs to this section."""
    request = context.get("request")
    classes = "nav-link"
    if request is None:
        return classes
    target = reverse(url_name)
    matches = request.path == target if exact or target == "/" else request.path.startswith(target)
    return classes + " is-active" if matches else classes


@register.filter
def short_name(user):
    """'Анна К.' — the public form of a person's name."""
    first = user.first_name or user.username
    return f"{first} {user.last_name[:1]}." if user.last_name else first


@register.filter
def uk_plural(number, forms):
    """{{ n|uk_plural:"оцінка,оцінки,оцінок" }} — Ukrainian plural forms."""
    one, few, many = forms.split(",")
    n = abs(int(number or 0))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


@register.simple_tag
def demo_mode():
    from django.conf import settings

    return settings.DEMO_MODE


@register.filter
def when(value):
    """One date format for the whole site: 'Пт, 25 вересня, 19:57' (year only if not current)."""
    from django.utils import timezone
    from django.utils.formats import date_format

    if not value:
        return ""
    local = timezone.localtime(value)
    pattern = "D, j E, H:i" if local.year == timezone.localtime().year else "D, j E Y, H:i"
    return date_format(local, pattern)


@register.filter
def ago(value):
    """'щойно', '5 хв тому', '3 год тому', otherwise the date — for feeds and chats."""
    from django.utils import timezone
    from django.utils.formats import date_format

    if not value:
        return ""
    seconds = (timezone.now() - value).total_seconds()
    if seconds < 60:
        return "щойно"
    if seconds < 3600:
        return f"{int(seconds // 60)} хв тому"
    if seconds < 86400:
        return f"{int(seconds // 3600)} год тому"
    local = timezone.localtime(value)
    pattern = "j E, H:i" if local.year == timezone.localtime().year else "j E Y"
    return date_format(local, pattern)
