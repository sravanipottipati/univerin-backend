from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from .models import Order, OrderItem, Notification, Cart
from .serializers import PlaceOrderSerializer, OrderSerializer
from vendors.models import Vendor, Product
from wallet.models import WalletTransaction
from django.utils import timezone


def create_notification(user, notif_type, title, message, order=None):
    try:
        Notification.objects.create(
            user=user,
            type=notif_type,
            title=title,
            message=message,
            order=order,
        )
    except Exception as e:
        print(f"Notification error: {e}")


class PlaceOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.user_type != 'buyer':
            return Response(
                {'error': 'Only buyers can place orders'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = PlaceOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        try:
            vendor = Vendor.objects.get(id=data['vendor_id'], status='approved')
        except Vendor.DoesNotExist:
            return Response(
                {'error': 'Shop not found or not approved'},
                status=status.HTTP_404_NOT_FOUND
            )
        total_amount = 0
        order_items  = []
        for item in data['items']:
            try:
                product  = Product.objects.get(
                    id=item['product_id'], vendor=vendor, is_available=True
                )
                quantity = int(item['quantity'])
                price    = float(item.get('price', product.price))
                total_amount += price * quantity
                variant = None
                if item.get('variant_id'):
                    try:
                        from vendors.models import ProductVariant
                        variant = ProductVariant.objects.get(id=item['variant_id'])
                    except Exception:
                        pass
                order_items.append({'product': product, 'quantity': quantity, 'price': price, 'variant': variant})
            except Product.DoesNotExist:
                return Response(
                    {'error': f"Product {item['product_id']} not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        # ── Fee Structure ──────────────────────────────────────
        # Platform fee
        platform_fee = 10  # flat ₹10

        # Use delivery fee from frontend (slab-based)
        delivery_fee = float(data.get('delivery_fee', 10))

        # Commission rate based on vendor category
        category = vendor.category.lower() if vendor.category else ''
        if category in ['vegetables', 'fruits']:
            commission_rate = 3.0
        elif category in ['restaurant', 'bakery', 'fast_food', 'chinese', 'ice_cream']:
            commission_rate = 20.0
        else:
            commission_rate = 6.0  # default groceries/supermarket

        subtotal         = float(total_amount)
        commission_amount = round(subtotal * commission_rate / 100, 2)
        gst_on_platform  = round((platform_fee + delivery_fee) * 18 / 100, 2)
        tcs_amount       = round(subtotal * 1 / 100, 2)
        platform_fee_gst = round(platform_fee * 1.18)
        delivery_fee_gst = round(delivery_fee * 1.18) if delivery_fee > 0 else 0
        grand_total      = round(subtotal + platform_fee_gst + delivery_fee_gst, 2)

        order = Order.objects.create(
            buyer=request.user,
            vendor=vendor,
            subtotal=subtotal,
            platform_fee=platform_fee,
            delivery_fee=delivery_fee,
            commission_rate=commission_rate,
            commission_amount=commission_amount,
            gst_on_platform=gst_on_platform,
            tcs_amount=tcs_amount,
            total_amount=grand_total,
            delivery_address=data['delivery_address'],
            instructions=data.get('instructions', ''),
            payment_mode=data.get('payment_mode', 'cod'),
            status='placed'
        )
        for item in order_items:
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                variant=item.get('variant'),
                quantity=item['quantity'],
                price=item['price']
            )
        # Notify vendor about new order
        create_notification(
            user=vendor.user,
            notif_type='new_order',
            title='New Order Received',
            message=f'Order #{str(order.id)[:8].upper()} received for ₹{order.total_amount}',
            order=order,
        )
        # Notify buyer order placed
        create_notification(
            user=request.user,
            notif_type='order_placed',
            title='Order Placed Successfully',
            message=f'Your order from {vendor.shop_name} has been placed!',
            order=order,
        )
        # ── Clear cart after successful order ──────────────────
        Cart.objects.filter(buyer=request.user, vendor=vendor).delete()

        return Response({
            'message': 'Order placed successfully!',
            'order': OrderSerializer(order).data
        }, status=status.HTTP_201_CREATED)


class BuyerOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders     = Order.objects.filter(buyer=request.user).order_by('-created_at')
        serializer = OrderSerializer(orders, many=True)
        return Response({'count': orders.count(), 'orders': serializer.data})


class VendorOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            vendor = request.user.vendor
        except Exception:
            return Response({'error': 'You do not have a shop'}, status=400)
        orders     = Order.objects.filter(vendor=vendor).order_by('-created_at')
        serializer = OrderSerializer(orders, many=True)
        return Response({'count': orders.count(), 'orders': serializer.data})


class UpdateOrderStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)
        new_status = request.data.get('status')
        user       = request.user
        # Vendor actions
        if user.user_type == 'vendor':
            try:
                vendor = user.vendor
            except Exception:
                return Response({'error': 'Not a vendor'}, status=400)
            if order.vendor != vendor:
                return Response({'error': 'This is not your order'}, status=403)
            allowed = ['accepted', 'rejected', 'preparing', 'dispatched', 'delivered']
            if new_status not in allowed:
                return Response({'error': f'Invalid status. Choose from: {allowed}'}, status=400)
            # Record platform fee when accepted
            if new_status == 'accepted' and order.status == 'placed':
                WalletTransaction.objects.create(
                    vendor=order.vendor,
                    order=order,
                    amount=order.platform_fee,
                    transaction_type='debit',
                    status='pending',
                    description=f'Platform fee for order {order.id}'
                )
            order.status = new_status
            order.save()
            # Notify buyer of status change
            STATUS_MESSAGES = {
                'accepted':   ('Order Accepted ✅',   f'{vendor.shop_name} accepted your order!'),
                'rejected':   ('Order Rejected ❌',   f'{vendor.shop_name} rejected your order.'),
                'preparing':  ('Being Prepared 👨‍🍳',  f'{vendor.shop_name} is preparing your order.'),
                'dispatched': ('Out for Delivery 🛵', 'Your order is on the way!'),
                'delivered':  ('Order Delivered 🎉',  'Your order has been delivered. Enjoy!'),
            }
            if new_status in STATUS_MESSAGES:
                title, message = STATUS_MESSAGES[new_status]
                create_notification(
                    user=order.buyer,
                    notif_type=f'order_{new_status}',
                    title=title,
                    message=message,
                    order=order,
                )
            return Response({
                'message': f'Order status updated to {new_status}',
                'order':   OrderSerializer(order).data
            })
        # Buyer cancel
        elif user.user_type == 'buyer':
            if order.buyer != user:
                return Response({'error': 'Not your order'}, status=403)
            if new_status != 'cancelled':
                return Response({'error': 'Buyers can only cancel orders'}, status=400)
            if order.status not in ['placed']:
                return Response({'error': 'Can only cancel orders that are just placed'}, status=400)
            order.status = 'cancelled'
            order.save()
            # Notify vendor of cancellation
            create_notification(
                user=order.vendor.user,
                notif_type='order_cancelled',
                title='Order Cancelled ❌',
                message=f'Order #{str(order.id)[:8].upper()} was cancelled by customer.',
                order=order,
            )
            return Response({'message': 'Order cancelled', 'order': OrderSerializer(order).data})
        return Response({'error': 'Unauthorized'}, status=403)


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)
        user = request.user
        if order.buyer != user and (
            not hasattr(user, 'vendor') or order.vendor != user.vendor
        ):
            return Response({'error': 'Unauthorized'}, status=403)
        return Response(OrderSerializer(order).data)


# ─── NOTIFICATION VIEWS ───────────────────────────────────────────────────────

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)[:50]
        data = [{
            'id':         str(n.id),
            'type':       n.type,
            'title':      n.title,
            'message':    n.message,
            'is_read':    n.is_read,
            'order_id':   str(n.order.id) if n.order else None,
            'created_at': n.created_at.isoformat(),
        } for n in notifications]
        return Response({
            'count':         len(data),
            'unread':        sum(1 for n in data if not n['is_read']),
            'notifications': data,
        })


class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, notif_id=None):
        if notif_id:
            Notification.objects.filter(id=notif_id, user=request.user).update(is_read=True)
        else:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'Marked as read'})


class SubmitReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, buyer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)
        if order.status != 'delivered':
            return Response({'error': 'Can only review delivered orders'}, status=400)
        if hasattr(order, 'review'):
            return Response({'error': 'Already reviewed'}, status=400)
        rating  = request.data.get('rating', 5)
        comment = request.data.get('comment', '')
        from .models import Review
        review = Review.objects.create(
            order=order, buyer=request.user,
            vendor=order.vendor, rating=rating, comment=comment,
        )
        return Response({
            'message': 'Review submitted successfully!',
            'rating':  review.rating,
            'comment': review.comment,
        }, status=201)

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, buyer=request.user)
            if hasattr(order, 'review'):
                return Response({
                    'has_review': True,
                    'rating':     order.review.rating,
                    'comment':    order.review.comment,
                })
            return Response({'has_review': False})
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)


# ─── CART VIEWS ───────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_cart(request):
    cart_items = Cart.objects.filter(
        buyer=request.user
    ).select_related('product', 'vendor')

    data = []
    for item in cart_items:
        data.append({
            'id':            str(item.id),
            'product_id':    str(item.product.id),
            'product_name':  f"{item.product.name} ({item.variant.name})" if item.variant else item.product.name,
            'product_price': str(item.price) if item.price else str(item.product.price),
            'product_mrp':   str(item.variant.mrp) if item.variant and item.variant.mrp else (str(item.product.mrp) if item.product.mrp else None),
            'product_image': str(item.product.image) if item.product.image else '',
            'product_gst':   str(item.product.gst_percentage),
            'vendor_id':     str(item.vendor.id),
            'vendor_name':   item.vendor.shop_name,
            'quantity':      item.quantity,
            'subtotal':      str(item.subtotal),
        })
    total = sum(float(i['subtotal']) for i in data)
    return Response({
        'items': data,
        'total': round(total, 2),
        'count': len(data),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_to_cart(request):
    product_id = request.data.get('product_id')
    vendor_id  = request.data.get('vendor_id')
    variant_id = request.data.get('variant_id', None)
    price      = request.data.get('price', None)
    quantity   = int(request.data.get('quantity', 1))

    try:
        product = Product.objects.get(id=product_id)
        vendor  = Vendor.objects.get(id=vendor_id)
    except Product.DoesNotExist:
        return Response({'error': 'Product not found'}, status=404)
    except Vendor.DoesNotExist:
        return Response({'error': 'Vendor not found'}, status=404)

    variant = None
    if variant_id:
        try:
            from vendors.models import ProductVariant
            variant = ProductVariant.objects.get(id=variant_id)
        except Exception:
            pass

    cart_item, created = Cart.objects.get_or_create(
        buyer=request.user,
        product=product,
        variant=variant,
        defaults={'vendor': vendor, 'quantity': quantity, 'price': price}
    )
    if not created:
        cart_item.quantity += quantity
        if price: cart_item.price = price
        cart_item.save()

    return Response({
        'message':  'Added to cart',
        'quantity': cart_item.quantity,
        'cart_id':  str(cart_item.id),
    })


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_cart_item(request, item_id):
    try:
        item = Cart.objects.get(id=item_id, buyer=request.user)
    except Cart.DoesNotExist:
        return Response({'error': 'Cart item not found'}, status=404)

    quantity = int(request.data.get('quantity', 1))
    if quantity <= 0:
        item.delete()
        return Response({'message': 'Item removed from cart'})

    item.quantity = quantity
    item.save()
    return Response({
        'message':  'Cart updated',
        'quantity': item.quantity,
    })


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_from_cart(request, item_id):
    try:
        item = Cart.objects.get(id=item_id, buyer=request.user)
        item.delete()
        return Response({'message': 'Removed from cart'})
    except Cart.DoesNotExist:
        return Response({'error': 'Cart item not found'}, status=404)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def clear_cart(request):
    vendor_id = request.data.get('vendor_id') or request.query_params.get('vendor_id')
    if vendor_id:
        deleted_count, _ = Cart.objects.filter(buyer=request.user, vendor_id=vendor_id).delete()
    else:
        deleted_count, _ = Cart.objects.filter(buyer=request.user).delete()
    return Response({
        'message': f'Cart cleared ({deleted_count} items removed)'
    })

# ─── COUPON VIEWS ─────────────────────────────────────────────────────────────
from django.utils.timezone import now as tz_now

class ValidateCouponView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .models import Coupon
        code         = request.data.get('code', '').upper().strip()
        order_amount = float(request.data.get('order_amount', 0))

        if not code:
            return Response({'error': 'Coupon code required'}, status=400)

        try:
            coupon = Coupon.objects.get(
                code=code,
                is_active=True,
                valid_from__lte=tz_now(),
                valid_until__gte=tz_now(),
            )
        except Coupon.DoesNotExist:
            return Response({'error': 'Invalid or expired coupon'}, status=400)

        if coupon.used_count >= coupon.max_uses:
            return Response({'error': 'Coupon usage limit reached'}, status=400)

        if order_amount < float(coupon.min_order):
            return Response({
                'error': f'Minimum order amount is ₹{coupon.min_order}'
            }, status=400)

        if coupon.discount_type == 'percent':
            discount = round(order_amount * float(coupon.discount_value) / 100, 2)
        else:
            discount = float(coupon.discount_value)

        return Response({
            'valid':    True,
            'code':     coupon.code,
            'discount': discount,
            'message':  f'Coupon applied! You save ₹{discount}',
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_return(request, order_id):
    try:
        order = Order.objects.get(id=order_id, buyer=request.user)
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=404)
    if order.status != 'delivered':
        return Response({'error': 'Can only return delivered orders'}, status=400)
    reason  = request.data.get('reason', '')
    comment = request.data.get('comment', '')
    if not reason:
        return Response({'error': 'Please provide a reason'}, status=400)
    # Create notification for admin
    Notification.objects.create(
        user=request.user,
        title='Return Request Submitted',
        message=f'Return request for Order #{order.order_number}: {reason}',
        type='order',
    )
    return Response({
        'message': 'Return request submitted successfully! Refund will be processed in 5-7 business days.',
        'order_id': str(order.id),
        'reason': reason,
    })
