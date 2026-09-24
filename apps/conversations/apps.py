from django.apps import AppConfig


class ConversationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.conversations"
    verbose_name = "Розмови"

    def ready(self):
        from apps.moderation.services import register_reportable

        from .models import Message

        register_reportable("message", Message)
