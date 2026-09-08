from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from profiles.models import Profile


class ServiceStatusTests(APITestCase):
    def test_service_status_requires_auth(self):
        """Sin autenticación, el endpoint de estado de servicio debe rechazar."""
        r = self.client.get('/api/auth/service/status/')
        self.assertIn(r.status_code, (401, 403))

    def test_service_status_returns_profile(self):
        """Con usuario autenticado y Profile, devuelve el estado del servicio."""
        user = User.objects.create_user(username='u1', password='x', email='u1@test.com')
        Profile.objects.create(user=user)
        self.client.force_authenticate(user=user)
        r = self.client.get('/api/auth/service/status/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('service_status', r.data)
