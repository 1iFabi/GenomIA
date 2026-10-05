from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from profiles.models import Profile, ServiceStatus
from services.legacy_profile import get_legacy_service_projection
from .models import AppUser, EmailVerification, WelcomeStatus, PasswordResetToken


class ProfileInline(admin.StackedInline):
    """Inline para mostrar el Profile dentro del User admin"""
    model = Profile
    can_delete = False
    verbose_name = 'Perfil'
    verbose_name_plural = 'Perfil'
    fields = ('phone', 'projected_service_status')
    readonly_fields = ('projected_service_status',)

    @admin.display(description='Estado servicio')
    def projected_service_status(self, obj):
        if obj.user_id is None:
            return ServiceStatus.NO_PURCHASED
        return get_legacy_service_projection(obj.user).service_status


class AppUserInline(admin.StackedInline):
    """Assign one GenomIA role without making Django staff flags into app privileges."""
    model = AppUser
    fields = ('role',)
    can_delete = False
    extra = 1
    max_num = 1
    verbose_name = 'GenomIA functional role'
    verbose_name_plural = 'GenomIA functional role'


class CustomUserAdmin(BaseUserAdmin):
    """Admin personalizado para User que incluye perfil y rol funcional."""
    inlines = (ProfileInline, AppUserInline)

    def get_inlines(self, request, obj):
        # The post_save hook creates CLIENTE on User creation; exposing a second
        # AppUser form on the add page would try to create a duplicate mapping.
        return (ProfileInline,) if obj is None else super().get_inlines(request, obj)

    # Columnas mostradas en la lista
    list_display = (
        'username', 'email', 'first_name', 'last_name',
        'get_phone', 'get_service_status', 'is_staff', 'is_active', 'date_joined'
    )
    list_filter = ('is_staff', 'is_active', 'date_joined',)
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)

    # Campos editables en el formulario
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Información personal', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas importantes', {'fields': ('last_login', 'date_joined')}),
    )

    def get_phone(self, obj):
        """Obtiene el teléfono del Profile relacionado"""
        try:
            return obj.profile.phone or '-'
        except Profile.DoesNotExist:
            return '-'
    get_phone.short_description = 'Teléfono'

    def get_service_status(self, obj):
        return get_legacy_service_projection(obj).service_status
    get_service_status.short_description = 'Estado servicio'


# Desregistrar el UserAdmin por defecto y registrar el personalizado
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ('email', 'user', 'is_verified', 'created_at', 'expires_at', 'is_expired')
    list_filter = ('is_verified', 'created_at')
    search_fields = ('email', 'user__username')
    readonly_fields = ('token', 'created_at', 'verified_at')
    ordering = ('-created_at',)

    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = 'Expirado'


@admin.register(WelcomeStatus)
class WelcomeStatusAdmin(admin.ModelAdmin):
    list_display = ('user', 'welcome_sent', 'sent_at')
    list_filter = ('welcome_sent', 'sent_at')
    search_fields = ('user__username', 'user__email')


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'used', 'is_expired')
    list_filter = ('used', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('token', 'created_at')
    ordering = ('-created_at',)

    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = 'Expirado'
