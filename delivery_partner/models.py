from django.db import models
from cloudinary.models import CloudinaryField
from users.models import User
import uuid


class DeliveryPartner(models.Model):
    """
    DP-specific profile data — vehicle details and KYC documents.
    Linked one-to-one to the existing User model (user_type='delivery_partner').
    Authentication itself is handled entirely by the users app (see Section 1).
    """

    VEHICLE_CHOICES = (
        ('bike',    'Bike'),
        ('scooter', 'Scooter'),
        ('bicycle', 'Bicycle'),
    )

    STATUS_CHOICES = (
        ('pending_kyc',          'Pending KYC'),
        ('pending_verification', 'Pending Verification'),
        ('approved',             'Approved'),
        ('rejected',             'Rejected'),
    )

    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='delivery_partner')

    vehicle_type    = models.CharField(max_length=10, choices=VEHICLE_CHOICES, blank=True, null=True)
    vehicle_number  = models.CharField(max_length=20, blank=True, null=True)

    aadhaar_number           = models.CharField(max_length=12, blank=True, null=True)
    aadhaar_document          = CloudinaryField('image', folder='univerin/dp_documents/aadhaar', blank=True, null=True)
    pan_number                = models.CharField(max_length=10, blank=True, null=True)
    pan_document               = CloudinaryField('image', folder='univerin/dp_documents/pan', blank=True, null=True)
    driving_licence_number    = models.CharField(max_length=20, blank=True, null=True)
    driving_licence_document  = CloudinaryField('image', folder='univerin/dp_documents/dl', blank=True, null=True)
    selfie_photo               = CloudinaryField('image', folder='univerin/dp_documents/selfie', blank=True, null=True)

    status           = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pending_kyc')
    rejection_reason = models.TextField(blank=True, null=True)

    is_online = models.BooleanField(default=False)
    current_latitude = models.FloatField(null=True, blank=True)
    current_longitude = models.FloatField(null=True, blank=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "delivery_partner_profiles"
        verbose_name = "Delivery Partner Profile"
        verbose_name_plural = "Delivery Partner Profiles"

    def __str__(self):
        return f"{self.user.full_name} ({self.user.phone_number}) — {self.status}"

    def has_all_documents(self):
        return bool(
            self.aadhaar_document and self.driving_licence_document and
            self.selfie_photo and self.vehicle_type and self.vehicle_number
        )

    def submit_for_verification(self):
        if self.status == 'pending_kyc' and self.has_all_documents():
            self.status = 'pending_verification'
            self.save(update_fields=['status', 'updated_at'])