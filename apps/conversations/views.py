from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import is_moderator
from apps.moderation.models import Report

from . import services
from .models import Conversation, Message


def _get_conversation(request, pk):
    """
    Participants always; a moderator only when a message in it was reported
    (ADR 0007: private by default).
    """
    conversation = get_object_or_404(
        Conversation.objects.select_related("help_request", "recipient", "volunteer"), pk=pk
    )
    if conversation.is_participant(request.user):
        return conversation, False
    if is_moderator(request.user):
        message_ids = conversation.messages.values("pk")
        reported = Report.objects.filter(
            content_type=ContentType.objects.get_for_model(Message), object_id__in=message_ids
        ).exists()
        if reported:
            return conversation, True
    raise Http404


@login_required
def conversation_list(request):
    conversations = [c for c in services.conversations_for(request.user) if not c.is_archived]
    for conversation in conversations:
        conversation.partner = conversation.other(request.user)
        conversation.unread = conversation.has_unread(request.user)
    return render(request, "conversations/list.html", {"conversations": conversations})


@login_required
def conversation_detail(request, pk):
    conversation, as_moderator = _get_conversation(request, pk)
    if request.method == "POST":
        if as_moderator:
            raise Http404
        try:
            services.send(conversation, request.user, request.POST.get("body", ""))
        except services.ConversationError as exc:
            flash.error(request, str(exc))
        return redirect("conversations:detail", pk=pk)

    if not as_moderator:
        conversation.mark_read(request.user)
    history = list(services.visible_messages(conversation))
    return render(
        request,
        "conversations/detail.html",
        {
            "conversation": conversation,
            "partner": conversation.other(request.user),
            "history": history,
            "last_id": history[-1].pk if history else 0,
            "as_moderator": as_moderator,
            "can_write": conversation.is_writable and not as_moderator,
            "phone_shared": conversation.messages.filter(
                sender=request.user, kind=Message.Kind.PHONE
            ).exists(),
            "max_length": services.MAX_LENGTH,
        },
    )


@login_required
@require_GET
@never_cache
def messages_json(request, pk):
    conversation, as_moderator = _get_conversation(request, pk)
    try:
        after = int(request.GET.get("after", 0))
    except ValueError:
        after = 0
    new = [
        services.serialize(m, request.user) for m in services.visible_messages(conversation, after)
    ]
    if new and not as_moderator:
        conversation.mark_read(request.user)
    return JsonResponse({"messages": new, "writable": conversation.is_writable})


@login_required
@require_POST
def share_phone(request, pk):
    conversation, as_moderator = _get_conversation(request, pk)
    if as_moderator:
        raise Http404
    try:
        services.share_phone(conversation, request.user)
    except services.ConversationError as exc:
        flash.error(request, str(exc))
    return redirect("conversations:detail", pk=pk)
