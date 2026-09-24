from django.contrib import admin

from .models import Conversation

# Message is deliberately not registered: bodies are private and reached only via reports


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    """Metadata only: message texts are private (ADR 0007) and reviewed via reports."""

    list_display = ("help_request", "recipient", "volunteer", "last_message_at")
    raw_id_fields = ("help_request", "recipient", "volunteer")
    list_select_related = ("help_request", "recipient", "volunteer")
    exclude = (
        "recipient_read_at",
        "volunteer_read_at",
        "recipient_notified_at",
        "volunteer_notified_at",
    )
