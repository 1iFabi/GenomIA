from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from accounts.roles import grant_reception_role


class ReceptionTests(APITestCase):
    def test_reception_requires_auth(self):
        """Sin autenticación, los endpoints de recepción deben rechazar."""
        r = self.client.get('/api/reception/search/')
        self.assertIn(r.status_code, (401, 403))

    def test_reception_search_allows_reception(self):
        """Un usuario con rol de recepción puede buscar."""
        user = User.objects.create_user(username='rec', password='x', email='rec@test.com')
        grant_reception_role(user)
        self.client.force_authenticate(user=user)
        r = self.client.get('/api/reception/search/?email=rec@test.com')
        self.assertEqual(r.status_code, 200)
