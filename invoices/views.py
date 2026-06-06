from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from orders.models import Order
from datetime import date, timedelta

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def buyer_invoice(request, order_id):
    from .invoice_generator import generate_buyer_invoice
    try:
        order = Order.objects.get(id=order_id, buyer=request.user)
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=404)
    buffer = generate_buyer_invoice(order)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="invoice_{str(order.id)[:8].upper()}.pdf"'
    return response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def commission_invoice(request, order_id):
    from .invoice_generator import generate_commission_invoice
    try:
        vendor = request.user.vendor
        order = Order.objects.get(id=order_id, vendor=vendor)
    except Exception:
        return Response({'error': 'Order not found'}, status=404)
    buffer = generate_commission_invoice(order)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="commission_{str(order.id)[:8].upper()}.pdf"'
    return response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seller_dashboard_invoice(request, order_id):
    from .invoice_generator import generate_seller_dashboard_invoice
    try:
        vendor = request.user.vendor
        order = Order.objects.get(id=order_id, vendor=vendor)
    except Exception:
        return Response({'error': 'Order not found'}, status=404)
    try:
        buffer = generate_seller_dashboard_invoice(order)
    except Exception as e:
        import traceback
        print("PDF ERROR:", traceback.format_exc())
        return Response({'error': str(e)}, status=500)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="seller_invoice_{str(order.id)[:8].upper()}.pdf"'
    return response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def settlement_statement(request):
    from .invoice_generator import generate_settlement_statement
    try:
        vendor = request.user.vendor
    except Exception:
        return Response({'error': 'Vendor not found'}, status=404)
    today = date.today()
    last_monday = today - timedelta(days=today.weekday()+7)
    last_sunday = last_monday + timedelta(days=6)
    buffer = generate_settlement_statement(vendor, last_monday, last_sunday)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="settlement_{vendor.shop_name}.pdf"'
    return response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tcs_certificate(request):
    from .invoice_generator import generate_tcs_certificate
    try:
        vendor = request.user.vendor
    except Exception:
        return Response({'error': 'Vendor not found'}, status=404)
    today = date.today()
    q = (today.month - 1) // 3 + 1
    quarter_starts = {1: date(today.year,1,1), 2: date(today.year,4,1), 3: date(today.year,7,1), 4: date(today.year,10,1)}
    quarter_ends   = {1: date(today.year,3,31), 2: date(today.year,6,30), 3: date(today.year,9,30), 4: date(today.year,12,31)}
    quarter_names  = {1:'Q1', 2:'Q2', 3:'Q3', 4:'Q4'}
    buffer = generate_tcs_certificate(vendor, quarter_starts[q], quarter_ends[q], quarter_names[q])
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="tcs_{vendor.shop_name}.pdf"'
    return response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def platform_invoice(request, order_id):
    from .invoice_generator import generate_platform_invoice
    try:
        order = Order.objects.get(id=order_id, buyer=request.user)
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=404)
    try:
        buffer = generate_platform_invoice(order)
    except Exception as e:
        import traceback
        print("Platform invoice ERROR:", traceback.format_exc())
        return Response({'error': str(e)}, status=500)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="platform_{str(order.id)[:8].upper()}.pdf"'
    return response
