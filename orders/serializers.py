from rest_framework import serializers
from .models import Order, OrderItem
from vendors.serializers import ProductSerializer

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    product_mrp  = serializers.SerializerMethodField()

    def get_product_name(self, obj):
        return obj.product.name

    def get_product_mrp(self, obj):
        return str(obj.product.mrp) if obj.product.mrp else None

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_mrp', 'quantity', 'price']

class PlaceOrderSerializer(serializers.Serializer):
    vendor_id = serializers.UUIDField()
    delivery_address = serializers.CharField()
    instructions = serializers.CharField(required=False, allow_blank=True)
    payment_mode = serializers.ChoiceField(choices=['cod', 'online'], default='cod')
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
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)
    shop_name = serializers.CharField(source='vendor.shop_name', read_only=True)
    class Meta:
        model = Order
        fields = ['id', 'order_number', 'buyer_name', 'shop_name', 'vendor_id', 'status', 'total_amount',
                  'platform_fee', 'delivery_fee', 'delivery_address', 'instructions',
                  'payment_mode', 'gst_on_platform', 'subtotal', 'items', 'created_at', 'updated_at']
