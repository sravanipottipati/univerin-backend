from django.db import models
from users.models import User
from vendors.models import Vendor, Product
import uuid


# ── Readable order number like UNI-250401-7823 ────────────────────────────────
def generate_order_number(vendor=None):
    from datetime import datetime
    import random, string
    date = datetime.now().strftime("%y%m%d")
    # Get shop initials from vendor
    if vendor and hasattr(vendor, 'shop_name') and vendor.shop_name:
        words = vendor.shop_name.strip().split()
        initials = ''.join(w[0].upper() for w in words if w)[:3]
    else:
        initials = 'UNI'
    # Get today's order count for this vendor
    try:
        from django.utils import timezone
        today = timezone.now().date()
        # Count orders for this vendor today
        today_count = Order.objects.filter(
            vendor=vendor,
            created_at__date=today
        ).count() + 1
        seq = str(today_count).zfill(3)
    except Exception:
        seq = ''.join(random.choices(string.digits, k=3))
    return f"UNI-{date}-{initials}{seq}" if not Order.objects.filter(order_number=f"UNI-{date}-{initials}{seq}").exists() else f"UNI-{date}-{initials}{seq}{random.randint(1,9)}"


class Order(models.Model):
    STATUS_CHOICES = (
        ('placed',     'Placed'),
        ('accepted',   'Accepted'),
        ('rejected',   'Rejected'),
        ('preparing',  'Preparing'),
        ('dispatched', 'Dispatched'),
        ('delivered',  'Delivered'),
        ('cancelled',  'Cancelled'),
    )
    PAYMENT_CHOICES = (
        ('cod',    'Cash on Delivery'),
        ('online', 'Online Payment'),
    )

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number     = models.CharField(max_length=20, unique=True, default=generate_order_number, editable=False)
    buyer            = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    vendor           = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='orders')
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='placed')
    total_amount     = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee     = models.DecimalField(max_digits=6, decimal_places=2, default=10)
    delivery_fee     = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    gst_on_delivery  = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    commission_rate  = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    commission_amount= models.DecimalField(max_digits=8, decimal_places=2, default=0)
    gst_on_platform  = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    tcs_amount       = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    subtotal         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_address = models.TextField()
    instructions     = models.TextField(blank=True, null=True)
    payment_mode          = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='cod')
    payment_status        = models.CharField(max_length=20, default='pending')
    razorpay_order_id     = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id   = models.CharField(max_length=100, blank=True, null=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order_number} — {self.buyer.full_name} from {self.vendor.shop_name}"


class OrderItem(models.Model):
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order    = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product  = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant  = models.ForeignKey('vendors.ProductVariant', on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField(default=1)
    price    = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"


class Notification(models.Model):
    TYPE_CHOICES = (
        ('order_placed',     'Order Placed'),
        ('order_accepted',   'Order Accepted'),
        ('order_rejected',   'Order Rejected'),
        ('order_preparing',  'Order Preparing'),
        ('order_dispatched', 'Order Dispatched'),
        ('order_delivered',  'Order Delivered'),
        ('order_cancelled',  'Order Cancelled'),
        ('new_order',        'New Order'),
        ('settlement',       'Settlement'),
    )

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type       = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title      = models.CharField(max_length=200)
    message    = models.TextField()
    order      = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.full_name} - {self.title}"


class Review(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order      = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='review')
    buyer      = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='reviews')
    vendor     = models.ForeignKey('vendors.Vendor', on_delete=models.CASCADE, related_name='reviews')
    rating     = models.IntegerField(default=5)
    comment    = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.db.models import Avg
        avg   = Review.objects.filter(vendor=self.vendor).aggregate(Avg('rating'))['rating__avg']
        count = Review.objects.filter(vendor=self.vendor).count()
        self.vendor.rating        = round(avg, 1)
        self.vendor.total_reviews = count
        self.vendor.save()

    def __str__(self):
        return f"{self.buyer.full_name} → {self.vendor.shop_name} ({self.rating}★)"


# ─── CART MODEL ───────────────────────────────────────────────────────────────
class Cart(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cart_items')
    product    = models.ForeignKey(Product, on_delete=models.CASCADE)
    vendor     = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='cart_items')
    variant    = models.ForeignKey('vendors.ProductVariant', on_delete=models.SET_NULL, null=True, blank=True)
    price      = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    quantity   = models.PositiveIntegerField(default=1)
    added_at   = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('buyer', 'product', 'variant')
        ordering        = ['-added_at']

    def __str__(self):
        return f"{self.buyer.full_name} - {self.product.name} x{self.quantity}"

    @property
    def subtotal(self):
        p = self.price if self.price else self.product.price
        return p * self.quantity


# ─── COUPON MODEL ─────────────────────────────────────────────────────────────
class Coupon(models.Model):
    DISCOUNT_TYPES = (
        ('percent', 'Percentage'),
        ('flat',    'Flat Amount'),
    )

    code           = models.CharField(max_length=20, unique=True)
    discount_type  = models.CharField(max_length=10, choices=DISCOUNT_TYPES, default='percent')
    discount_value = models.DecimalField(max_digits=6, decimal_places=2)
    min_order      = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    max_uses       = models.PositiveIntegerField(default=100)
    used_count     = models.PositiveIntegerField(default=0)
    valid_from     = models.DateTimeField()
    valid_until    = models.DateTimeField()
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} ({self.discount_type} - {self.discount_value})"
# ─── RETURN REQUEST MODEL ─────────────────────────────────────────────────────
class ReturnRequest(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order      = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='return_request')
    buyer      = models.ForeignKey('users.User', on_delete=models.CASCADE)
    reason     = models.CharField(max_length=255)
    comment    = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Return for {self.order.order_number}"


class Refund(models.Model):
    STATUS_CHOICES = (
        ('requested', 'Requested'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
        ('processed', 'Processed'),
    )
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order        = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='refund')
    requested_by = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='refunds')
    reason       = models.TextField()
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')
    admin_note   = models.TextField(blank=True, null=True)
    approved_by  = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_refunds')
    requested_at = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Refund for {self.order.order_number} - {self.status}"
