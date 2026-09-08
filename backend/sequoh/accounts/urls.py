from django.urls import path
from .views import (
    LoginAPIView,
    CsrfCookieAPIView,
    RegisterAPIView,
    ResendVerificationAPIView,
    PasswordResetRequestAPIView,
    PasswordResetConfirmAPIView,
    MeAPIView,
    ChangePasswordAPIView,
    LogoutAPIView,
    DashboardAPIView,
    DeleteAccountAPIView,
    ContactAPIView,
    UserServiceStatusAPIView,
    AdminStatsAPIView,
    GetUsersAPIView,
    ManageAnalystRoleAPIView,
)

urlpatterns = [
    # Autenticación / cuentas
    path('auth/csrf/', CsrfCookieAPIView.as_view(), name='api_csrf'),
    path('auth/login/', LoginAPIView.as_view(), name='api_login'),
    path('auth/register/', RegisterAPIView.as_view(), name='api_register'),
    path('auth/resend-verification/', ResendVerificationAPIView.as_view(), name='api_resend_verification'),
    path('auth/password-reset/', PasswordResetRequestAPIView.as_view(), name='api_password_reset'),
    path('auth/password-reset-confirm/', PasswordResetConfirmAPIView.as_view(), name='api_password_reset_confirm'),
    path('auth/me/', MeAPIView.as_view(), name='api_me'),
    path('auth/me/change-password/', ChangePasswordAPIView.as_view(), name='api_change_password'),
    path('auth/me/delete-account/', DeleteAccountAPIView.as_view(), name='api_delete_account'),
    path('auth/logout/', LogoutAPIView.as_view(), name='api_logout'),
    path('auth/dashboard/', DashboardAPIView.as_view(), name='api_dashboard'),
    path('auth/service/status/', UserServiceStatusAPIView.as_view(), name='api_service_status'),

    # Contacto
    path('contact/', ContactAPIView.as_view(), name='api_contact'),

    # Administración
    path('admin/stats/', AdminStatsAPIView.as_view(), name='api_admin_stats'),
    path('admin/analysts/', ManageAnalystRoleAPIView.as_view(), name='api_admin_manage_analysts'),
    path('admin/users/', GetUsersAPIView.as_view(), name='api_get_users'),
]
