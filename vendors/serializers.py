from rest_framework import serializers
from .models import Vendor, Product, ProductVariant
import math

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two GPS coordinates using Haversine formula"""
    R    = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a    = (math.sin(dlat/2) ** 2 +
            math.cos(math.radians(lat1)) *
            math.cos(math.radians(lat2)) *
            math.sin(dlon/2) ** 2)
    c    = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

# ─── PRODUCT VARIANT SERIALIZER ───────────────────────────────────────────────
class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ProductVariant
        fields = ['id', 'name', 'price', 'mrp', 'stock_quantity', 'is_available']

# ─── PRODUCT SERIALIZER ───────────────────────────────────────────────────────
class ProductSerializer(serializers.ModelSerializer):
    variants  = ProductVariantSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = ['id', 'name', 'description', 'price', 'mrp', 'gst_percentage', 'category',
                  'is_available', 'is_veg', 'image', 'image_url', 'variants', 'created_at',
                  'hsn_code', 'subcategory', 'is_returnable', 'is_cod', 'is_draft', 'delivery_time',
                  'barcode', 'brand', 'manufacturer', 'net_weight', 'ingredients', 'nutritional_info', 'allergen_info', 'expiry_date']

    def get_image_url(self, obj):
        if obj.image:
            return obj.image.url
        return None

# ─── VENDOR SERIALIZER ────────────────────────────────────────────────────────
class VendorSerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True, read_only=True)
    distance = serializers.SerializerMethodField()

    class Meta:
        model  = Vendor
        fields = ['id', 'shop_name', 'category', 'description',
                  'phone_number', 'address', 'town',
                  'latitude', 'longitude',
                  'delivery_type', 'estimated_delivery_time',
                  'delivery_radius',                          # ← NEW
                  'rating', 'total_reviews', 'platform_fee',
                  'is_open', 'status', 'products',
                  'distance', 'created_at',
                  'bank_account_name', 'bank_account_number', 'bank_ifsc_code', 'bank_name',
                  'min_order_value', 'min_order', 'gstin', 'pan', 'fssai_number']

    min_order_value = serializers.SerializerMethodField()

    def get_min_order_value(self, obj):
        return float(obj.min_order) if obj.min_order else 100

    def get_distance(self, obj):
        request = self.context.get('request')
        if not request:
            return None
        try:
            lat_str = request.query_params.get('lat')
            lng_str = request.query_params.get('lng')
            if not lat_str or not lng_str:
                return None
            buyer_lat = float(lat_str)
            buyer_lng = float(lng_str)
            if not obj.latitude or not obj.longitude:
                return None
            dist = calculate_distance(buyer_lat, buyer_lng, obj.latitude, obj.longitude)
            return dist
        except (ValueError, TypeError) as e:
            print(f"Distance error: {e}")
            return None

# ─── VENDOR REGISTER SERIALIZER ───────────────────────────────────────────────
class VendorRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Vendor
        fields = ['shop_name', 'category', 'description',
                  'phone_number', 'address', 'town',
                  'latitude', 'longitude',
                  'delivery_type', 'estimated_delivery_time',
                  'delivery_radius',
                  'gstin', 'pan', 'fssai_number']

    def create(self, validated_data):
        user     = self.context['request'].user
        fee_map  = {
            'vegetables':  5,
            'fruits':      5,
            'dairy':       5,
            'bakery':      7,
            'grocery':     7,
            'restaurant':  10,
            'supermarket': 7,
            'other':       7,
        }
        category     = validated_data.get('category', 'other')
        platform_fee = fee_map.get(category, 7)
        vendor = Vendor.objects.create(
            user=user,
            platform_fee=platform_fee,
            **validated_data
        )
        return vendor

# ─── ADD PRODUCT SERIALIZER ───────────────────────────────────────────────────
class AddProductSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Product
        fields = ['name', 'description', 'price', 'mrp', 'gst_percentage', 'category', 'is_available', 'is_veg', 'image', 'hsn_code', 'subcategory', 'is_returnable', 'is_cod', 'is_draft', 'delivery_time',
                  'barcode', 'brand', 'manufacturer', 'net_weight', 'ingredients', 'nutritional_info', 'allergen_info', 'expiry_date']

# ─── ADD VARIANT SERIALIZER ───────────────────────────────────────────────────
class AddVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ProductVariant
        fields = ['name', 'price', 'mrp', 'stock_quantity', 'is_available']