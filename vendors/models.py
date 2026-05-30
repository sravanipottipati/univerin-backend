from django.db import models
from users.models import User
from cloudinary.models import CloudinaryField
import uuid


class Vendor(models.Model):
    CATEGORY_CHOICES = (
        ('restaurant',  'Restaurant'),
        ('supermarket', 'Supermarket'),
        ('bakery',      'Bakery'),
        ('veg_fruits',  'Veg & Fruits'),
    )
    DELIVERY_CHOICES = (
        ('delivery', 'Delivery'),
        ('pickup',   'Pickup'),
        ('both',     'Both'),
    )
    STATUS_CHOICES = (
        ('pending',  'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    id                      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # ── Bank Details ──────────────────────────────────────────
    bank_account_name   = models.CharField(max_length=200, blank=True, null=True)
    bank_account_number = models.CharField(max_length=20,  blank=True, null=True)
    bank_ifsc_code      = models.CharField(max_length=11,  blank=True, null=True)
    bank_name           = models.CharField(max_length=100, blank=True, null=True)
    user                    = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vendor')
    shop_name               = models.CharField(max_length=200)
    category                = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description             = models.TextField(blank=True, null=True)
    phone_number            = models.CharField(max_length=10)
    address                 = models.TextField()
    town                    = models.CharField(max_length=100)
    latitude                = models.FloatField(null=True, blank=True)
    longitude               = models.FloatField(null=True, blank=True)
    delivery_type           = models.CharField(max_length=10, choices=DELIVERY_CHOICES, default='both')
    estimated_delivery_time = models.IntegerField(default=30)
    # ── NEW: Vendor delivery radius in km ─────────────────────────────────────
    delivery_radius         = models.FloatField(default=5.0)
    # ─────────────────────────────────────────────────────────────────────────
    platform_fee            = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    wallet_balance          = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rating                  = models.FloatField(default=0.0)
    total_reviews           = models.IntegerField(default=0)
    is_open                 = models.BooleanField(default=True)
    status                  = models.CharField(max_length=10, choices=STATUS_CHOICES, default='approved')
    created_at              = models.DateTimeField(auto_now_add=True)
    updated_at              = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.shop_name} ({self.town})"


class Product(models.Model):
    CATEGORY_CHOICES = (
        ('vegetables',    'Vegetables'),
        ('fruits',        'Fruits'),
        ('dairy',         'Dairy'),
        ('bakery',        'Bakery'),
        ('snacks',        'Snacks'),
        ('beverages',     'Beverages'),
        ('food',          'Food'),
        ('grocery',       'Grocery'),
        ('restaurant',    'Restaurant'),
        ('supermarket',   'Supermarket'),
        ('fast_food',     'Fast Food'),
        ('chinese',       'Chinese'),
        ('ice_cream',     'Ice Cream'),
        ('fresh_leafies', 'Fresh Leafies'),
        ('fresh_veggies', 'Fresh Veggies'),
        ('staples',       'Staples'),
        ('dal_pulses',    'Dal & Pulses'),
        ('oils',          'Oils'),
        ('spices',        'Spices'),
        ('masala_powders','Masala Powders'),
        ('sugar_salt',    'Sugar & Salt'),
        ('dry_fruits',    'Dry Fruits'),
        ('milk',          'Milk'),
        ('curd',          'Curd'),
        ('butter',        'Butter'),
        ('paneer',        'Paneer'),
        ('ghee',          'Ghee'),
        ('eggs',          'Eggs'),
        ('breakfast',     'Breakfast'),
        ('lunch',         'Lunch'),
        ('dinner',        'Dinner'),
        ('main_course',   'Main Course'),
        ('biryani',       'Biryani'),
        ('other',         'Other'),
    )
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor       = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='products')
    name         = models.CharField(max_length=200)
    description  = models.TextField(blank=True, null=True)
    price        = models.DecimalField(max_digits=8, decimal_places=2)
    mrp          = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text='Original price before discount')
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='GST % e.g. 5, 12, 18')
    category     = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    is_available = models.BooleanField(default=True)
    is_veg       = models.BooleanField(default=True)  # True=Veg, False=Non-veg
    image        = CloudinaryField('image', folder='shop2me/products', blank=True, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)
    hsn_code       = models.CharField(max_length=20, blank=True, null=True)
    subcategory    = models.CharField(max_length=100, blank=True, null=True)
    is_returnable  = models.BooleanField(default=True)
    is_cod         = models.BooleanField(default=True)
    is_draft       = models.BooleanField(default=False)
    delivery_time  = models.PositiveIntegerField(default=30)

    def __str__(self):
        return f"{self.name} - {self.vendor.shop_name}"

    def get_image_url(self):
        if self.image:
            return self.image.url
        return None


# ─── PRODUCT VARIANTS ─────────────────────────────────────────────────────────
class ProductVariant(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product        = models.ForeignKey(
                         Product, on_delete=models.CASCADE,
                         related_name='variants')
    name           = models.CharField(max_length=100)
    price          = models.DecimalField(max_digits=8, decimal_places=2)
    mrp            = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=100)
    is_available   = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)


    class Meta:
        ordering = ['price']

    def __str__(self):
        return f"{self.product.name} — {self.name} (₹{self.price})"


# ─── WISHLIST ─────────────────────────────────────────────────────────────────
class Wishlist(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist')
    product    = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='wishlisted_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.full_name} - {self.product.name}"