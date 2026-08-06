from django.urls import path
from . import views

urlpatterns = [
    path("dp/onboarding/vehicle/",   views.DPOnboardingVehicleView.as_view()),
    path("dp/onboarding/documents/", views.DPOnboardingDocumentsView.as_view()),
    path("dp/onboarding/status/",    views.DPOnboardingStatusView.as_view()),
]