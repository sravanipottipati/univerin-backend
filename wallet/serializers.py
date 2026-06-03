from rest_framework import serializers
from .models import WalletTransaction

class WalletTransactionSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source='order.id', read_only=True)
    order_number = serializers.SerializerMethodField()
    net_settlement = serializers.SerializerMethodField()

    class Meta:
        model = WalletTransaction
        fields = ['id', 'order_id', 'order_number', 'amount', 'net_settlement',
                  'transaction_type', 'status', 'description', 'settled_at', 'created_at']

    def get_order_number(self, obj):
        return obj.order.order_number if obj.order else None

    def get_net_settlement(self, obj):
        if not obj.order:
            return float(obj.amount)
        o = obj.order
        subtotal = float(o.subtotal or 0)
        commission = float(o.commission_amount or 0)
        tcs = float(o.tcs_amount or 0)
        net = subtotal - commission - tcs
        return round(net, 2)
