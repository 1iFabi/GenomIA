from unittest.mock import patch

from rest_framework.test import APITestCase
from django.contrib.auth.models import User


class ReportTests(APITestCase):
    def test_legacy_payload_builder_and_imports_are_absent(self):
        from reports import views

        for name in ('_build_report_payload', 'UserSNP', 'build_rsid_extra_info_map'):
            with self.subTest(name=name):
                self.assertFalse(hasattr(views, name))

    def test_report_requires_auth(self):
        """Sin autenticación, el endpoint del reporte debe rechazar."""
        r = self.client.get('/api/report/pdf/')
        self.assertIn(r.status_code, (401, 403))

    def test_authenticated_report_is_unavailable_without_payload_or_generation(self):
        self.client.force_authenticate(user=User(username='report-reader'))

        with patch('reports.views._build_report_payload', create=True, side_effect=AssertionError(
            'Unavailable PDF must not build a report payload',
        )) as build_payload, patch('subprocess.run', side_effect=AssertionError(
            'Unavailable PDF must not launch the generator',
        )) as run_generator, self.assertNumQueries(0):
            response = self.client.get('/api/report/pdf/')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json(), {
            'code': 'pdf_report_unavailable',
            'detail': 'El reporte PDF estará disponible cuando los resultados hayan sido revisados y publicados.',
        })
        build_payload.assert_not_called()
        run_generator.assert_not_called()
