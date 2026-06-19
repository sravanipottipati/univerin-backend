from django.urls import path
from .views import (RegisterView, LoginView, ProfileView,
                    AddressListView, AddressDetailView, SetDefaultAddressView,
                    UploadProfilePhotoView, ForgotPasswordView, ResetPasswordView,
                    VerifyOTPView, delete_account_request, make_admin, save_push_token)
from rest_framework_simplejwt.views import TokenRefreshView
from .admin_views import admin_stats
from . import admin_views

urlpatterns = [
    # ─── AUTH ─────────────────────────────────────────────────────────────────
    path('register/',                            RegisterView.as_view(),           name='register'),
    path('login/',                               LoginView.as_view(),              name='login'),
    path('token/refresh/',                       TokenRefreshView.as_view(),       name='token_refresh'),
    path('forgot-password/',                     ForgotPasswordView.as_view(),     name='forgot-password'),
    path('reset-password/',                      ResetPasswordView.as_view(),      name='reset-password'),
    path('verify-otp/',                           VerifyOTPView.as_view(),          name='verify-otp'),
    path('save-push-token/',                      save_push_token,                  name='save-push-token'),
    # ─── PROFILE ──────────────────────────────────────────────────────────────
    path('profile/',                             ProfileView.as_view(),            name='profile'),
    path('profile/photo/',                       UploadProfilePhotoView.as_view(), name='profile-photo'),
    # ─── ADDRESSES ────────────────────────────────────────────────────────────
    path('addresses/',                           AddressListView.as_view(),        name='addresses'),
    path('addresses/<uuid:address_id>/',         AddressDetailView.as_view(),      name='address-detail'),
    path('addresses/<uuid:address_id>/default/', SetDefaultAddressView.as_view(),  name='address-default'),
    path('admin/stats/',                       admin_stats,                          name='admin-stats'),
    path('delete-account-request/',              delete_account_request,          name='delete-account-request'),
    path('make-admin/',                          make_admin,                name='make-admin'),
    path('admin/sellers/',                       admin_views.admin_sellers_list,  name='admin-sellers'),
    path('admin/sellers/<uuid:vendor_id>/verify/', admin_views.admin_verify_seller, name='admin-verify-seller'),
]