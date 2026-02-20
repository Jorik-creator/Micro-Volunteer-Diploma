from django.contrib import admin
from .models import Category, HelpRequest, Response


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


class ResponseInline(admin.TabularInline):
    model = Response
    extra = 0
    readonly_fields = ('volunteer', 'status', 'message', 'created_at')


@admin.register(HelpRequest)
class HelpRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'category', 'urgency', 'status', 'needed_date', 'created_at')
    list_filter = ('status', 'urgency', 'category', 'created_at')
    search_fields = ('title', 'description', 'recipient__username', 'recipient__email')
    date_hierarchy = 'created_at'
    inlines = [ResponseInline]
    actions = ['mark_expired', 'mark_cancelled']

    @admin.action(description='Позначити як прострочені')
    def mark_expired(self, request, queryset):
        queryset.filter(status=HelpRequest.Status.ACTIVE).update(status=HelpRequest.Status.EXPIRED)

    @admin.action(description='Скасувати вибрані запити')
    def mark_cancelled(self, request, queryset):
        queryset.exclude(status=HelpRequest.Status.COMPLETED).update(status=HelpRequest.Status.CANCELLED)


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ('volunteer', 'help_request', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('volunteer__username', 'help_request__title')
