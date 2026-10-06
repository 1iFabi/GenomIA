from django.apps import apps
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from profiles.models import Profile
from services.status import ClientStatus, get_service_projection
from services.models import ServiceRequest, ServiceStatus, Sample, Purchase
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
            return ClientStatus.NO_PURCHASED
        return get_service_projection(obj.user).service_status


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
        return get_service_projection(obj).service_status
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


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ('purchase', 'participant', 'status', 'created_at', 'completed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('participant__user__email', 'purchase__owner__django_user__email')
    readonly_fields = ('purchase', 'participant', 'created_at', 'started_at')


admin.site.register(ServiceStatus)
admin.site.register(Sample)
admin.site.register(Purchase)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Browse-only: service state must change through the API so every step is logged."""
    list_select_related = True

    def get_list_display(self, request):
        return [field.name for field in self.model._meta.concrete_fields][:8]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Participant questionnaires/answers stay out of the admin by design (privacy).
HIDDEN_FROM_ADMIN = {'participants.ParticipantMetadata'}
for app_label in ('accounts', 'services', 'participants', 'genoma', 'reception'):
    for model in apps.get_app_config(app_label).get_models():
        # Django admin cannot register composite-primary-key models.
        if (not admin.site.is_registered(model) and not model._meta.is_composite_pk
                and model._meta.label not in HIDDEN_FROM_ADMIN):
            admin.site.register(model, ReadOnlyAdmin)
