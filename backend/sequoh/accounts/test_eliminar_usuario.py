from django.contrib.auth.models import User
from django.test import TestCase

from accounts.management.commands.eliminar_usuario import delete_user_completely
from accounts.roles import grant_analyst_role
from genoma.client_results import populate_client_results
from genoma.models import Analysis, AnalysisResult, Genotype, Variant, VariantAnnotation, VariantPlacement
from participants.models import Participant
from profiles.models import Profile
from services.models import Purchase, Sample, ServiceRequest, ServiceStatusLog


class DeleteUserCompletelyTests(TestCase):
    def setUp(self):
        self.analyst = User.objects.create_user(username='delete-analyst')
        grant_analyst_role(self.analyst)
        self.user = User.objects.create_user(username='delete-client', email='delete@example.com')
        for index in range(12):
            variant = Variant.objects.create(variant_type='SNV')
            position = 1_000 + index * 6_000_000
            VariantPlacement.objects.create(variant=variant, reference_assembly='GRCh38', contig='1',
                                            start_pos=position, end_pos=position, reference_allele='C',
                                            alternate_allele='T')
            VariantAnnotation.objects.create(
                variant=variant, source_name='ClinVar', source_version='1', annotation_type='clinvar',
                clinical_significance='Pathogenic' if index % 4 == 0 else 'Benign',
                payload={'info': {'CLNDN': 'Some_disease', 'GENEINFO': 'GENE1:1', 'RS': str(index)}},
            )

    def test_removes_the_user_and_everything_that_depends_on_it_but_nothing_else(self):
        populate_client_results(self.user, 10, seed=1)
        owned = {
            'participants': Participant.objects.filter(user=self.user),
            'purchases': Purchase.objects.filter(owner__django_user=self.user),
            'services': ServiceRequest.objects.filter(purchase__owner__django_user=self.user),
            'samples': Sample.objects.filter(participant__user=self.user),
            'analyses': Analysis.objects.filter(participant__user=self.user),
            'genotypes': Genotype.objects.filter(participant__user=self.user),
            'results': AnalysisResult.objects.filter(analysis__participant__user=self.user),
        }
        self.assertTrue(all(queryset.exists() for queryset in owned.values()))
        status_logs = ServiceStatusLog.objects.filter(request__in=owned['services']).count()
        self.assertGreater(status_logs, 0)

        counts = delete_user_completely(self.user)

        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Profile.objects.filter(user_id=self.user.pk).exists())
        for name, queryset in owned.items():
            with self.subTest(name=name):
                self.assertFalse(queryset.model.objects.filter(pk__in=queryset.values('pk')).exists())
        self.assertEqual(counts['auth.User'], 1)
        self.assertEqual(Variant.objects.count(), 12)
        self.assertTrue(User.objects.filter(pk=self.analyst.pk).exists())
