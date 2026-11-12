from django.contrib import admin
from .models import User

@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'phone_number', 'user_type', 'is_active']
    list_filter = ['user_type', 'is_active']
    search_fields = ['full_name', 'phone_number']
    ordering = ['full_name']
    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        ('Personal Info', {'fields': ('full_name', 'email')}),
        ('Permissions', {'fields': ('user_type', 'is_active', 'is_admin', 'is_staff')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'phone_number', 'full_name',
                'password1', 'password2', 'user_type'
            ),
        }),
    )


# Account deletion requests: review only.
# Actual deletion must be performed through a separate,
# verified administrative fulfillment process.
from .models import AccountDeletionRequest


@admin.register(AccountDeletionRequest)
class AccountDeletionRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "account_type",
        "status",
        "requested_at",
        "completed_at",
    )
    list_filter = ("account_type", "status", "requested_at")
    search_fields = ("user__phone_number", "user__full_name")
    readonly_fields = (
        "id",
        "user",
        "account_type",
        "status",
        "retention_summary",
        "failure_reason",
        "requested_at",
        "completed_at",
    )
    ordering = ("-requested_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
