from django.contrib import admin

from services.legacy_profile import get_legacy_service_projection
from .models import Profile, ServiceStatus


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'projected_service_status', 'projected_service_updated_at')
    search_fields = ('user__username', 'user__email', 'phone')
    list_filter = ('user__date_joined',)
    exclude = ('service_status', 'service_updated_at')
    readonly_fields = ('projected_service_status', 'projected_service_updated_at')

    def _projection(self, obj):
        if obj.user_id is None:
            return None
        # Both list columns share one projection per Profile instance.
        if not hasattr(obj, '_admin_service_projection'):
            obj._admin_service_projection = get_legacy_service_projection(obj.user)
        return obj._admin_service_projection

    @admin.display(description='Estado servicio')
    def projected_service_status(self, obj):
        projection = self._projection(obj)
        return projection.service_status if projection else ServiceStatus.NO_PURCHASED

    @admin.display(description='Estado actualizado')
    def projected_service_updated_at(self, obj):
        projection = self._projection(obj)
        return projection.updated_at if projection else None
