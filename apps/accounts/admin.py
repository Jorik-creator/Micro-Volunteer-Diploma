from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import RecipientProfile, User, VolunteerProfile


class VolunteerProfileInline(admin.StackedInline):
    model = VolunteerProfile
    can_delete = False


class RecipientProfileInline(admin.StackedInline):
    model = RecipientProfile
    can_delete = False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'user_type',
        'is_verified',
        'is_active',
    )
    list_filter = ('user_type', 'is_verified', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            'Додаткова інформація',
            {
                'fields': (
                    'user_type',
                    'phone',
                    'address',
                    'latitude',
                    'longitude',
                    'date_of_birth',
                    'avatar',
                    'is_verified',
                ),
            },
        ),
    )

    def get_inlines(self, request, obj=None):
        """Show the appropriate profile inline based on user type."""
        if obj is None:
            return []
        if obj.is_volunteer:
            return [VolunteerProfileInline]
        if obj.is_recipient:
            return [RecipientProfileInline]
        return []


@admin.register(VolunteerProfile)
class VolunteerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'radius_km', 'is_available')
    list_filter = ('is_available', 'radius_km')


@admin.register(RecipientProfile)
class RecipientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'situation_type')
    list_filter = ('situation_type',)
