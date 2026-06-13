from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum, Count
from datetime import datetime
from orders.models import Order
from users.models import User

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_stats(request):
    if not request.user.user_type == 'admin':
        return Response({'error': 'Admin access required'}, status=403)

    month = int(request.GET.get('month', datetime.now().month))
    year  = int(request.GET.get('year', datetime.now().year))

    # All time stats
    total_orders   = Order.objects.count()
    total_revenue  = Order.objects.filter(status='delivered').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_vendors  = User.objects.filter(user_type='vendor').count()
    total_buyers   = User.objects.filter(user_type='buyer').count()

    # This month stats
    month_orders  = Order.objects.filter(created_at__month=month, created_at__year=year).count()
    month_revenue = Order.objects.filter(status='delivered', created_at__month=month, created_at__year=year).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    month_delivered = Order.objects.filter(status='delivered', created_at__month=month, created_at__year=year).count()
    month_cancelled = Order.objects.filter(status='cancelled', created_at__month=month, created_at__year=year).count()
    month_pending   = Order.objects.filter(status='pending', created_at__month=month, created_at__year=year).count()

    # Commission this month
    month_commission = Order.objects.filter(status='delivered', created_at__month=month, created_at__year=year).aggregate(Sum('commission_amount'))['commission_amount__sum'] or 0
    month_tcs        = Order.objects.filter(status='delivered', created_at__month=month, created_at__year=year).aggregate(Sum('tcs_amount'))['tcs_amount__sum'] or 0

    return Response({
        'all_time': {
            'total_orders':  total_orders,
            'total_revenue': float(total_revenue),
            'total_vendors': total_vendors,
            'total_buyers':  total_buyers,
        },
        'this_month': {
            'month':           month,
            'year':            year,
            'total_orders':    month_orders,
            'total_revenue':   float(month_revenue),
            'delivered':       month_delivered,
            'cancelled':       month_cancelled,
            'pending':         month_pending,
            'commission':      float(month_commission),
            'tcs':             float(month_tcs),
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_sellers_list(request):
    """Admin gets all sellers with FSSAI details"""
    from vendors.models import Vendor
    vendors = Vendor.objects.all().order_by('-created_at')
    data = []
    for v in vendors:
        data.append({
            'id': str(v.id),
            'shop_name': v.shop_name,
            'category': v.category,
            'phone_number': v.phone_number,
            'town': v.town,
            'gstin': v.gstin or '',
            'fssai_number': v.fssai_number or '',
            'fssai_certificate': v.fssai_certificate.url if v.fssai_certificate else '',
            'status': v.status,
            'is_verified': v.status == 'approved',
            'created_at': v.created_at.strftime('%d %b %Y'),
        })
    return Response({'sellers': data, 'total': len(data)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_verify_seller(request, vendor_id):
    """Admin approves or rejects seller"""
    from vendors.models import Vendor
    try:
        vendor = Vendor.objects.get(id=vendor_id)
        action = request.data.get('action')  # 'approve' or 'reject'
        if action == 'approve':
            vendor.status = 'approved'
            vendor.save()
            return Response({'message': f'{vendor.shop_name} approved!'})
        elif action == 'reject':
            vendor.status = 'rejected'
            vendor.save()
            return Response({'message': f'{vendor.shop_name} rejected!'})
        else:
            return Response({'error': 'Invalid action'}, status=400)
    except Vendor.DoesNotExist:
        return Response({'error': 'Vendor not found'}, status=404)
