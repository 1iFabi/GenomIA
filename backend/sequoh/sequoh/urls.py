"""
URL configuration for sequoh project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from accounts.allauth_views import CustomConfirmEmailView


def status_view(request):
    return JsonResponse({"status": "ok"})


def index(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path('', index, name='index'),
    path('api/status/', status_view, name='api_status'),
    path('ciff/', admin.site.urls),
    path('CIFF/', admin.site.urls),
    # Esta línea incluye las URLs de tu aplicación de autenticación
    path('api/', include('accounts.urls')),
    path('api/', include('reception.urls')),
    path('api/', include('genetics.urls')),
    path('api/', include('reports.urls')),
    # Sobreescribir la URL de confirmación de allauth para usar nuestro view personalizado
    path('accounts/confirm-email/<str:key>/', CustomConfirmEmailView.as_view(), name='account_confirm_email'),
    path('accounts/', include('allauth.urls')),
]




