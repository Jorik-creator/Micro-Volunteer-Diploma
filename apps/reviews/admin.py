from django.contrib import admin
from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('author', 'target', 'help_request', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('author__username', 'target__username', 'comment')
    readonly_fields = ('created_at',)
