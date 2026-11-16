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

    actions = ["process_selected_deletion_requests"]

    def has_view_permission(self, request, obj=None):
        return bool(
            request.user.is_active
            and request.user.is_staff
            and getattr(request.user, "is_admin", False)
        )

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    @admin.action(description="Process selected deletion requests")
    def process_selected_deletion_requests(self, request, queryset):
        from django.contrib import messages
        from users.deletion.processor import process_deletion_request

        if not self.has_view_permission(request):
            self.message_user(
                request,
                "Administrator authorization required.",
                level=messages.ERROR,
            )
            return

        completed = 0
        pending = 0
        failed = 0

        for deletion_request in queryset:
            try:
                result = process_deletion_request(
                    deletion_request.pk,
                    approved_by=request.user,
                )
                if result.status == "completed":
                    completed += 1
                else:
                    pending += 1
            except Exception:
                failed += 1

        self.message_user(
            request,
            (
                f"Completed: {completed}; "
                f"Pending cleanup: {pending}; "
                f"Blocked or failed: {failed}."
            ),
            level=messages.WARNING if failed else messages.INFO,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
