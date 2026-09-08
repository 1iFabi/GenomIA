from rest_framework.test import APITestCase
from django.contrib.auth.models import User


class ReportTests(APITestCase):
    def test_report_requires_auth(self):
        """Sin autenticación, el endpoint del reporte debe rechazar."""
        r = self.client.get('/api/report/pdf/')
        self.assertIn(r.status_code, (401, 403))
