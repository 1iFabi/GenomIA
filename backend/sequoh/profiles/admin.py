from django.contrib import admin
from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'service_status', 'service_updated_at')
    search_fields = ('user__username', 'user__email', 'phone')
    list_filter = ('user__date_joined', 'service_status')
