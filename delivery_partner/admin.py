from django.contrib import admin
from .models import DeliveryPartner


@admin.register(DeliveryPartner)
class DeliveryPartnerAdmin(admin.ModelAdmin):
    list_display   = ['user', 'vehicle_type', 'vehicle_number', 'status', 'is_online', 'created_at']
    list_filter    = ['status', 'vehicle_type', 'is_online']
    search_fields  = ['user__full_name', 'user__phone_number', 'vehicle_number']
    list_editable  = ['status']
    readonly_fields = ['created_at', 'updated_at', 'current_latitude', 'current_longitude', 'location_updated_at']
    fieldsets = (
        ('Delivery Partner', {'fields': ('user', 'status', 'rejection_reason')}),
        ('Vehicle', {'fields': ('vehicle_type', 'vehicle_number')}),
        ('Documents', {'fields': (
            'aadhaar_number', 'aadhaar_document',
            'pan_number', 'pan_document',
            'driving_licence_number', 'driving_licence_document',
            'selfie_photo',
        )}),
        ('Live Status', {'fields': ('is_online', 'current_latitude', 'current_longitude', 'location_updated_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )