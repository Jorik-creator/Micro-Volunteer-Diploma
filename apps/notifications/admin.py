from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'title', 'is_read', 'created_at')
    list_filter = ('type', 'is_read', 'created_at')
    search_fields = ('user__username', 'title', 'message')
    readonly_fields = ('created_at',)
    actions = ['mark_as_read']

    @admin.action(description='Позначити як прочитані')
    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)
