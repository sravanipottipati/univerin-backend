from django.urls import path
from . import views
from orders import dp_views as order_dp_views

urlpatterns = [
    path("dp/onboarding/vehicle/",   views.DPOnboardingVehicleView.as_view()),
    path("dp/onboarding/documents/", views.DPOnboardingDocumentsView.as_view()),
    path("dp/onboarding/status/",    views.DPOnboardingStatusView.as_view()),
    path("dp/duty/toggle/",          views.DPDutyToggleView.as_view()),
    path("dp/location/update/",      views.DPLocationUpdateView.as_view()),

    # ─── Order flow ──────────────────────────────────────────────
    path("dp/orders/available/",                       order_dp_views.DPAvailableOrdersView.as_view()),
    path("dp/orders/active/",                           order_dp_views.DPMyActiveOrderView.as_view()),
    path("dp/orders/<uuid:order_id>/accept/",           order_dp_views.DPOrderAcceptView.as_view()),
    path("dp/orders/<uuid:order_id>/reject/",           order_dp_views.DPOrderRejectView.as_view()),
    path("dp/orders/<uuid:order_id>/status/",           order_dp_views.DPOrderStatusUpdateView.as_view()),
    path("dp/orders/<uuid:order_id>/verify-delivery-otp/", order_dp_views.DPVerifyDeliveryOTPView.as_view()),
]