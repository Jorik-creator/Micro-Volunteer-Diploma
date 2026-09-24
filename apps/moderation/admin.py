from django.contrib import admin

from .models import InviteCode, Report, VerificationRequest


@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "city", "organization", "created_at", "reviewed_by")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "user__email", "city", "organization")
    raw_id_fields = ("user", "reviewed_by", "invite_code")
    list_select_related = ("user", "reviewed_by")


@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "organization", "uses_count", "max_uses", "expires_at", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "organization")
    readonly_fields = ("uses_count",)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("reason", "content_type", "object_id", "reporter", "status", "created_at")
    list_filter = ("status", "reason", "content_type")
    raw_id_fields = ("reporter", "resolved_by")
    list_select_related = ("reporter", "content_type")
