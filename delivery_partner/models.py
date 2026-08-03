from django.db import models
from django.utils import timezone


class DeliveryPartner(models.Model):
    """
    Core Delivery Partner account.
    Status progresses: pending_profile -> pending_kyc -> pending_verification -> approved / rejected
    """

    STATUS_CHOICES = [
        ("pending_profile", "Pending Profile"),
        ("pending_kyc", "Pending KYC"),
        ("pending_verification", "Pending Verification"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    ]

    # Auth
    phone_number = models.CharField(max_length=15, unique=True, db_index=True)
    is_phone_verified = models.BooleanField(default=False)

    # Profile (filled in Section 1, after OTP verified)
    full_name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True)

    # Status tracking
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending_profile")

    # Duty status (used later in Section 3, included here so migration doesn't need to run twice)
    is_online = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "delivery_partners"
        verbose_name = "Delivery Partner"
        verbose_name_plural = "Delivery Partners"

    def __str__(self):
        return f"{self.full_name or 'Unnamed'} ({self.phone_number})"

    def mark_profile_complete(self):
        if self.status == "pending_profile":
            self.status = "pending_kyc"
            self.save(update_fields=["status", "updated_at"])


class DeliveryPartnerOTP(models.Model):
    """
    Tracks OTP requests for both registration and login.
    Keep this separate from DeliveryPartner so unverified attempts don't
    create partial accounts.
    """

    PURPOSE_CHOICES = [
        ("register", "Registration"),
        ("login", "Login"),
    ]

    phone_number = models.CharField(max_length=15, db_index=True)
    purpose = models.CharField(max_length=10, choices=PURPOSE_CHOICES)
    session_id = models.CharField(max_length=100, blank=True)  # 2Factor.in session id
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "delivery_partner_otps"

    def is_expired(self):
        return timezone.now() > self.expires_at