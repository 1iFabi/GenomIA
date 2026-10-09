from django.urls import path
from .views import (
    LoginAPIView,
    CsrfCookieAPIView,
    RegisterAPIView,
    RegistrationEmailValidationAPIView,
    PasswordResetRequestAPIView,
    PasswordResetConfirmAPIView,
    MeAPIView,
    ChangePasswordAPIView,
    LogoutAPIView,
    DeleteAccountAPIView,
    ContactAPIView,
    AdminStatsAPIView,
    GetUsersAPIView,
    ManageAnalystRoleAPIView,
    PurchaseProfileAPIView,
)
from .google_auth import GoogleCompleteSignupAPIView, GoogleLoginAPIView

urlpatterns = [
    # Autenticación / cuentas
    path('auth/csrf/', CsrfCookieAPIView.as_view(), name='api_csrf'),
    path('auth/login/', LoginAPIView.as_view(), name='api_login'),
    path('auth/register/', RegisterAPIView.as_view(), name='api_register'),
    path('auth/register/email-validation/', RegistrationEmailValidationAPIView.as_view(), name='api_register_email_validation'),
    path('auth/password-reset/', PasswordResetRequestAPIView.as_view(), name='api_password_reset'),
    path('auth/password-reset-confirm/', PasswordResetConfirmAPIView.as_view(), name='api_password_reset_confirm'),
    path('auth/google/', GoogleLoginAPIView.as_view(), name='api_google_login'),
    path('auth/google/complete/', GoogleCompleteSignupAPIView.as_view(), name='api_google_complete'),
    path('auth/me/', MeAPIView.as_view(), name='api_me'),
    path('auth/me/purchase-profile/', PurchaseProfileAPIView.as_view(), name='api_purchase_profile'),
    path('auth/me/change-password/', ChangePasswordAPIView.as_view(), name='api_change_password'),
    path('auth/me/delete-account/', DeleteAccountAPIView.as_view(), name='api_delete_account'),
    path('auth/logout/', LogoutAPIView.as_view(), name='api_logout'),

    # Contacto
    path('contact/', ContactAPIView.as_view(), name='api_contact'),

    # Administración
    path('admin/stats/', AdminStatsAPIView.as_view(), name='api_admin_stats'),
    path('admin/analysts/', ManageAnalystRoleAPIView.as_view(), name='api_admin_manage_analysts'),
    path('admin/users/', GetUsersAPIView.as_view(), name='api_get_users'),
]
