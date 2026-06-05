from rest_framework import serializers
from .models import Order, OrderItem
from vendors.serializers import ProductSerializer

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    product_mrp  = serializers.SerializerMethodField()
    product_gst  = serializers.SerializerMethodField()

    def get_product_name(self, obj):
        if obj.variant:
            return f"{obj.product.name} ({obj.variant.name})"
        return obj.product.name

    def get_product_mrp(self, obj):
        if obj.variant and obj.variant.mrp:
            return str(obj.variant.mrp)
        return str(obj.product.mrp) if obj.product.mrp else None

    def get_product_gst(self, obj):
        return str(obj.product.gst_percentage) if obj.product.gst_percentage else '0'

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_mrp', 'product_gst', 'quantity', 'price']

class PlaceOrderSerializer(serializers.Serializer):
    vendor_id = serializers.UUIDField()
    delivery_address = serializers.CharField()
    instructions = serializers.CharField(required=False, allow_blank=True)
    payment_mode = serializers.ChoiceField(choices=['cod', 'online'], default='cod')
    delivery_fee = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, default=0)
    total        = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    items = serializers.ListField(
        child=serializers.DictField()
    )
    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Order must have at least one item")
        for item in items:
            if 'product_id' not in item:
                raise serializers.ValidationError("Each item needs a product_id")
            if 'quantity' not in item:
                raise serializers.ValidationError("Each item needs a quantity")
        return items

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    buyer_name  = serializers.CharField(source='buyer.full_name', read_only=True)
    buyer_phone = serializers.CharField(source='buyer.phone_number', read_only=True)
    shop_name = serializers.CharField(source='vendor.shop_name', read_only=True)
    has_review = serializers.SerializerMethodField()
    has_return = serializers.SerializerMethodField()

    def get_has_review(self, obj):
        return hasattr(obj, 'review')

    def get_has_return(self, obj):
        return hasattr(obj, 'return_request')

    class Meta:
        model = Order
        fields = ['id', 'order_number', 'buyer_name', 'buyer_phone', 'shop_name', 'vendor_id', 'status', 'total_amount', 'commission_rate', 'commission_amount', 'tcs_amount',
                  'platform_fee', 'delivery_fee', 'gst_on_delivery', 'delivery_address', 'instructions',
                  'payment_mode', 'gst_on_platform', 'subtotal', 'items', 'created_at', 'updated_at', 'has_review', 'has_return']
