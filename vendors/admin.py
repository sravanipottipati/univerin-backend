from django.contrib import admin
from .models import Vendor, Product, ProductVariant


# ─── PRODUCT VARIANT INLINE ───────────────────────────────────────────────────
class ProductVariantInline(admin.TabularInline):
    model       = ProductVariant
    extra       = 1
    fields      = ['name', 'price', 'stock_quantity', 'is_available']
    show_change_link = True


# ─── PRODUCT INLINE ───────────────────────────────────────────────────────────
class ProductInline(admin.TabularInline):
    model  = Product
    extra  = 0
    fields = ['name', 'price', 'category', 'is_available']
    show_change_link = True


# ─── VENDOR ADMIN ─────────────────────────────────────────────────────────────
@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display   = ['shop_name', 'category', 'town', 'status', 'is_open', 'gstin', 'fssai_number', 'rating', 'created_at']
    list_filter    = ['status', 'category', 'town', 'is_open']
    search_fields  = ['shop_name', 'town', 'gstin', 'fssai_number']
    list_editable  = ['status', 'is_open']
    readonly_fields = ['created_at', 'rating', 'total_reviews']
    fieldsets = (
        ('Basic Info', {'fields': ('shop_name', 'category', 'description', 'phone_number', 'status', 'is_open')}),
        ('Location', {'fields': ('town', 'state', 'address', 'latitude', 'longitude')}),
        ('Compliance', {'fields': ('gstin', 'pan', 'fssai_number', 'fssai_certificate')}),
        ('Bank Details', {'fields': ('bank_name', 'bank_account_name', 'bank_account_number', 'bank_ifsc_code')}),
        ('Stats', {'fields': ('rating', 'total_reviews', 'created_at')}),
    )
    inlines        = [ProductInline]


# ─── PRODUCT ADMIN ────────────────────────────────────────────────────────────
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display   = ['name', 'vendor', 'price', 'category', 'is_available', 'created_at']
    list_filter    = ['category', 'is_available', 'vendor']
    search_fields  = ['name', 'vendor__shop_name']
    list_editable  = ['price', 'is_available']
    inlines        = [ProductVariantInline]


# ─── PRODUCT VARIANT ADMIN ────────────────────────────────────────────────────
@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display  = ['product', 'name', 'price', 'stock_quantity', 'is_available']
    list_filter   = ['is_available']
    search_fields = ['product__name', 'name']
    list_editable = ['price', 'stock_quantity', 'is_available']