from django.contrib import admin, messages

from . import services
from .models import Category, HelpRequest, Response


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


class ResponseInline(admin.TabularInline):
    model = Response
    extra = 0
    readonly_fields = ("volunteer", "status", "status_reason", "message", "done_at", "created_at")
    can_delete = False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("volunteer")


@admin.register(HelpRequest)
class HelpRequestAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "recipient",
        "category",
        "urgency",
        "status",
        "needed_date",
        "created_at",
    )
    list_filter = ("status", "urgency", "category", "created_at")
    search_fields = ("title", "description", "recipient__username", "recipient__email")
    date_hierarchy = "created_at"
    inlines = [ResponseInline]
    list_select_related = ("recipient", "category")
    raw_id_fields = ("recipient",)
    # Status changes go through apps.requests.services so everyone gets notified
    readonly_fields = ("status", "status_changed_at", "completed_at", "reminder_sent_at")
    actions = ["close_as_moderator"]

    @admin.action(description="Закрити вибрані запити (порушення правил)")
    def close_as_moderator(self, request, queryset):
        closed = 0
        for help_request in queryset:
            try:
                services.cancel_by_moderator(help_request, "порушення правил платформи")
                closed += 1
            except services.TransitionError:
                pass
        self.message_user(request, f"Закрито запитів: {closed}", messages.SUCCESS)


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("volunteer", "help_request", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("volunteer__username", "help_request__title")
    list_select_related = ("volunteer", "help_request")
    raw_id_fields = ("volunteer", "help_request")
    readonly_fields = ("status", "status_reason", "done_at")
