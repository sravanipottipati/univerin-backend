from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
import uuid
import random
from django.utils import timezone
from datetime import timedelta

class UserManager(BaseUserManager):
    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('Phone number is required')
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_admin', True)
        extra_fields.setdefault('is_staff', True)
        return self.create_user(phone_number, password, **extra_fields)

class User(AbstractBaseUser):
    USER_TYPES = (
        ('buyer',  'Buyer'),
        ('vendor', 'Vendor'),
        ('admin',  'Admin'),
        ('delivery_partner', 'Delivery Partner'),
    )
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name     = models.CharField(max_length=100)
    phone_number  = models.CharField(max_length=10, unique=True)
    email         = models.EmailField(blank=True, null=True)
    user_type     = models.CharField(max_length=20, choices=USER_TYPES, default='buyer')
    is_active     = models.BooleanField(default=True)
    is_admin      = models.BooleanField(default=False)
    is_staff      = models.BooleanField(default=False)
    fcm_token     = models.TextField(blank=True, null=True)
    town          = models.CharField(max_length=100, blank=True, null=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD  = 'phone_number'
    REQUIRED_FIELDS = ['full_name']

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"

    def has_perm(self, perm, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True


class Address(models.Model):
    LABEL_CHOICES = (
        ('Home',  'Home'),
        ('Work',  'Work'),
        ('Other', 'Other'),
    )
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label        = models.CharField(max_length=50, choices=LABEL_CHOICES, default='Home')
    full_address = models.TextField()
    town         = models.CharField(max_length=100)
    state        = models.CharField(max_length=100, default='Andhra Pradesh')
    pincode      = models.CharField(max_length=10, blank=True, null=True)
    is_default   = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(
                user=self.user, is_default=True
            ).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.full_name} - {self.label} - {self.town}"


# ─── PASSWORD RESET OTP ───────────────────────────────────────────────────────
class PasswordResetOTP(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_otps')
    otp          = models.CharField(max_length=6)
    is_used      = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)
    expires_at   = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    @staticmethod
    def generate_otp():
        return str(random.randint(100000, 999999))

    def __str__(self):
        return f"{self.user.phone_number} - OTP: {self.otp}"