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