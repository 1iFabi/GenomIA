from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from profiles.models import Profile
from services.models import Purchase, PurchaseStatus, ServiceRequest, ServiceStatus, ServiceStatusLog


class ProfileAdminStatusTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_superuser(username='profile-operator', password='test-only')
        self.target = User.objects.create_user(username='profile-target')
        self.profile = Profile.objects.create(
            user=self.target, phone='original',
        )
        self.url = reverse('admin:profiles_profile_change', args=[self.profile.pk])
        self.client.force_login(self.operator)

    def test_list_and_detail_project_paid_service(self):
        paid = Purchase.objects.create(
            owner=self.target.app_user, status=PurchaseStatus.objects.get(code='PAID'),
            purchased_at=timezone.now(),
        )
        waiting = ServiceStatus.objects.get(code='WAITING_SAMPLE')
        request = ServiceRequest.objects.create(purchase=paid, status=waiting)
        log = ServiceStatusLog.objects.create(
            request=request, status=waiting, actor=self.operator.app_user,
        )
        listing = self.client.get(reverse('admin:profiles_profile_changelist'))
        self.assertEqual(listing.status_code, 200)
        admin = listing.context['cl'].model_admin
        self.assertNotIn('service_status', admin.list_filter)
        self.assertIn('projected_service_status', admin.list_display)
        self.assertNotIn('service_status', admin.list_display)
        self.assertEqual(admin.projected_service_status(self.profile), 'PENDING')
        self.assertEqual(admin.projected_service_updated_at(self.profile), log.changed_at)
        detail = self.client.get(self.url)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'PENDING')
        self.assertIn('projected_service_status', detail.context['adminform'].fieldsets[-1][1]['fields'])
        fields = detail.context['adminform'].form.fields
        self.assertIn('phone', fields)
        self.assertNotIn('service_status', fields)

        response = self.client.post(self.url, {
            'user': str(self.target.pk), 'phone': 'updated', '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302, response.context if response.status_code != 302 else None)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.phone, 'updated')

    def test_broken_newest_paid_fails_closed_in_list_and_detail(self):
        paid = PurchaseStatus.objects.get(code='PAID')
        earlier = Purchase.objects.create(
            owner=self.target.app_user, status=paid, purchased_at=timezone.now(),
        )
        waiting = ServiceStatus.objects.get(code='WAITING_SAMPLE')
        service = ServiceRequest.objects.create(purchase=earlier, status=waiting)
        ServiceStatusLog.objects.create(request=service, status=waiting, actor=self.operator.app_user)
        Purchase.objects.create(
            owner=self.target.app_user, status=paid, purchased_at=timezone.now(),
        )  # Latest paid is missing its service request.
        listing = self.client.get(reverse('admin:profiles_profile_changelist'))
        admin = listing.context['cl'].model_admin
        self.assertEqual(admin.projected_service_status(self.profile), 'NO_PURCHASED')
        self.assertEqual(admin.projected_service_updated_at(self.profile), None)
        self.assertContains(self.client.get(self.url), 'NO_PURCHASED')

    def test_no_paid_service_and_native_django_admin_access(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        listing = self.client.get(reverse('admin:profiles_profile_changelist'))
        self.assertEqual(listing.context['cl'].model_admin.projected_service_status(self.profile),
                         'NO_PURCHASED')
        self.assertContains(self.client.get(self.url), 'NO_PURCHASED')
        # A functional ADMIN role does not grant Django admin access by itself.
        functional_admin = User.objects.create_user(username='functional-only')
        functional_admin.app_user.role = Role.objects.get(code='ADMIN')
        functional_admin.app_user.save(update_fields=['role'])
        self.client.force_login(functional_admin)
        self.assertEqual(self.client.get(self.url).status_code, 302)
        staff_only = User.objects.create_user(username='staff-only', is_staff=True)
        self.client.force_login(staff_only)
        self.assertEqual(self.client.get(self.url).status_code, 403)

