from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import RecipientProfile, User, VolunteerProfile


class VolunteerProfileInline(admin.StackedInline):
    model = VolunteerProfile
    can_delete = False


class RecipientProfileInline(admin.StackedInline):
    model = RecipientProfile
    can_delete = False


@admin.action(description='Заблокувати обраних користувачів')
def block_users(modeladmin, request, queryset):
    eligible = queryset.filter(is_superuser=False)
    count = eligible.update(is_active=False)
    messages.success(request, f'Заблоковано {count} користувачів.')


@admin.action(description='Розблокувати обраних користувачів')
def unblock_users(modeladmin, request, queryset):
    count = queryset.update(is_active=True)
    messages.success(request, f'Розблоковано {count} користувачів.')


@admin.action(description='Позначити як верифікованих')
def verify_users(modeladmin, request, queryset):
    count = queryset.update(is_verified=True)
    messages.success(request, f'Верифіковано {count} користувачів.')


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    actions = [block_users, unblock_users, verify_users]
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
