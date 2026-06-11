from . import excel_views as views_excel
from django.urls import path
from . import views

urlpatterns = [
    path('export/seller/', views_excel.seller_monthly_excel, name='seller-excel'),
    path('export/admin/', views_excel.admin_billing_excel, name='admin-excel'),
    path('buyer/<uuid:order_id>/',           views.buyer_invoice,            name='buyer-invoice'),
    path('commission/<uuid:order_id>/',      views.commission_invoice,       name='commission-invoice'),
    path('seller/<uuid:order_id>/',          views.seller_dashboard_invoice, name='seller-invoice'),
    path('settlement/',                      views.settlement_statement,     name='settlement'),
    path('platform/<uuid:order_id>/',        views.platform_invoice,         name='platform-invoice'),
    path('export/platform-zip/',             views_excel.platform_invoices_zip,  name='platform-zip'),
    path('export/commission-zip/',           views_excel.commission_invoices_zip, name='commission-zip'),
    path('export/tcs-excel/',                views_excel.tcs_excel,               name='tcs-excel'),
    path('export/tds-excel/',                views_excel.tds_excel,               name='tds-excel'),
    path('tcs/',                             views.tcs_certificate,          name='tcs-certificate'),
    path('credit-note/<uuid:order_id>/',     views.credit_note,              name='credit-note'),
]
