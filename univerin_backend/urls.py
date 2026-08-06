from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

def ping(request):
    return JsonResponse({'status': 'ok'})

urlpatterns = [
    path('admin/',        admin.site.urls),
    path('api/users/',    include('users.urls')),
    path('api/vendors/',  include('vendors.urls')),
    path('api/invoices/', include('invoices.urls')),
    path('api/orders/',   include('orders.urls')),
    path('api/wallet/',   include('wallet.urls')),
    path('api/', include('delivery_partner.urls')),
    path('ping/',          ping),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)