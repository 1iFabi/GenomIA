import json

from django.conf import settings
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounts.jwt_utils import encode_jwt
from accounts.roles import grant_analyst_role
from genoma.client_results import (
    ANCESTRIES, CHR1_LENGTH, MIN_COHORT, PATHOGENIC, REFERENCE_POPULATIONS, TRAITS, populate_client_results,
    set_client_state,
)
from genoma.models import Analysis, Genotype, Variant, VariantAnnotation, VariantPlacement
from profiles.models import Profile, normalize_rut
from services.models import Purchase, ServiceRequest, ServiceStatusLog
from services.status import get_service_projection


class ClientResultsTests(APITestCase):
    def setUp(self):
        grant_analyst_role(User.objects.create_user(username='results-analyst'))
        self.user = User.objects.create_user(username='results-client', email='results@example.com')
        self.pathogenic = set()
        for index in range(40):
            variant = Variant.objects.create(variant_type='deletion' if index % 10 == 0 else 'SNV')
            position = 1_000 + index * 6_000_000
            VariantPlacement.objects.create(variant=variant, reference_assembly='GRCh38', contig='1',
                                            start_pos=position, end_pos=position, reference_allele='C',
                                            alternate_allele='T')
            significance = 'Pathogenic' if index % 8 == 0 else 'Benign'
            VariantAnnotation.objects.create(
                variant=variant, source_name='ClinVar', source_version='1', annotation_type='clinvar',
                clinical_significance=significance,
                payload={'info': {'CLNDN': 'Some_disease|not_provided', 'GENEINFO': 'GENE1:1', 'RS': str(index)}},
            )
            if significance == 'Pathogenic':
                self.pathogenic.add(str(variant.pk))

    def read(self, user):
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(user.pk)})
        return self.client.get('/api/genoma/v1/results/')

    def test_generated_results_are_complete_consistent_and_private(self):
        self.assertEqual(self.read(self.user).status_code, 404)
        summary = populate_client_results(self.user, 40, seed=1)
        self.assertEqual(get_service_projection(self.user).service_status, 'COMPLETED')
        response = self.read(self.user)
        self.assertEqual(response.status_code, 200, response.data)
        data = json.loads(json.dumps(response.data))
        modules = data['modules']
        self.assertEqual(data['sample_code'], summary['sample_code'])
        self.assertEqual(data['variant_summary'], {'total': 40, 'by_type': {'deletion': 4, 'SNV': 36}})

        for haplotype in (0, 1):
            segments = [s for s in modules['local_ancestry'] if s['haplotype'] == haplotype]
            self.assertEqual(segments[0]['start'], 1)
            self.assertEqual(segments[-1]['end'], CHR1_LENGTH)
            for before, after in zip(segments, segments[1:]):
                self.assertEqual(after['start'], before['end'] + 1)
        self.assertAlmostEqual(sum(g['proportion'] for g in modules['global_ancestry']), 1, places=4)
        countries = {(g['population'], g['country_code']) for g in modules['global_ancestry']}
        self.assertTrue(countries <= {(code, ref[2]) for code, ref in REFERENCE_POPULATIONS.items()})
        self.assertTrue(all(g['group'] in ANCESTRIES for g in modules['global_ancestry']))

        for variant in data['variants']:
            alleles = variant['genotype'].split('|')
            expected = [variant['local_ancestry'][f'haplotype_{h}']['population'] for h in (0, 1) if alleles[h] == '1']
            self.assertEqual(variant['alt_allele_ancestry'], expected)
            if variant['variant_id'] in self.pathogenic:
                self.assertEqual(variant['zygosity'], 'heterocigoto')
        self.assertEqual({m['variant_id'] for m in modules['monogenic_risk']}, self.pathogenic)
        self.assertTrue(all(m['gene'] == 'GENE1' and m['conditions'] == ['Some disease']
                            and m['clinical_significance'] in PATHOGENIC for m in modules['monogenic_risk']))
        self.assertEqual(len(modules['polygenic_risk']), 5)
        self.assertTrue(all(0 <= p['percentile'] <= 100 for p in modules['polygenic_risk']))
        self.assertEqual((len(modules['pharmacogenetics']), len(modules['traits'])), (5, len(TRAITS)))
        self.assertTrue(all(t['category'] and t['explanation'] and t['description'] for t in modules['traits']))
        for trait in modules['traits']:
            self.assertIn(trait['result'], [option['result'] for option in trait['options']])
            self.assertAlmostEqual(sum(option['frequency'] for option in trait['options']), 1)

        other = User.objects.create_user(username='results-other')
        self.assertEqual(self.read(other).status_code, 404)

    def test_rerun_replaces_the_previous_generated_run(self):
        populate_client_results(self.user, 30, seed=1)
        summary = populate_client_results(self.user, 20, seed=2)
        self.assertEqual(Purchase.objects.filter(owner__django_user=self.user).count(), 1)
        self.assertEqual(list(ServiceRequest.objects.filter(purchase__owner__django_user=self.user)
                              .values_list('pk', flat=True)), [summary['service_request_id']])
        self.assertEqual(Genotype.objects.filter(participant__user=self.user).count(), 20)
        self.assertEqual(Analysis.objects.filter(participant__user=self.user).values('module').distinct().count(),
                         Analysis.objects.filter(participant__user=self.user).count())
        self.assertEqual(self.read(self.user).data['variant_summary']['total'], 20)

    def test_ancestry_cohort_returns_aggregates_only_above_the_minimum(self):
        url = '/api/genoma/v1/results/ancestry-cohort/'
        self.client.cookies[settings.AUTH_COOKIE_NAME] = encode_jwt({'sub': str(self.user.pk)})
        self.assertEqual(self.client.get(url).status_code, 404)
        populate_client_results(self.user, 5, seed=0)
        for index in range(MIN_COHORT - 1):
            populate_client_results(User.objects.create_user(username=f'cohort-{index}'), 5, seed=index + 1)
        self.assertEqual(self.client.get(url).data, {'cohort_size': MIN_COHORT - 1, 'min_cohort': MIN_COHORT,
                                                     'populations': {}})
        populate_client_results(User.objects.create_user(username='cohort-last'), 5, seed=99)
        data = self.client.get(url).data
        self.assertEqual(data['cohort_size'], MIN_COHORT)
        self.assertEqual(set(data['populations']), set(REFERENCE_POPULATIONS))
        for stats in data['populations'].values():
            self.assertEqual(set(stats), {'mean', 'carriers', 'percentile'})
            self.assertTrue(0 <= stats['percentile'] <= 100 and 0 <= stats['mean'] <= 1)

    def test_client_can_be_moved_forward_and_back_through_every_state(self):
        expected = {'registrado': ('NO_PURCHASED', False), 'datos_compra': ('NO_PURCHASED', True),
                    'WAITING_SAMPLE': ('PENDING', True), 'SAMPLE_RECEIVED': ('PENDING', True),
                    'PROCESSING': ('PENDING', True)}
        for state in ('datos_compra', 'PROCESSING', 'COMPLETED', 'WAITING_SAMPLE', 'SAMPLE_RECEIVED',
                      'registrado', 'PROCESSING'):
            with self.subTest(state=state):
                if state == 'COMPLETED':
                    populate_client_results(self.user, 5, seed=1)
                    self.assertEqual(get_service_projection(self.user).service_status, 'COMPLETED')
                    self.assertEqual(self.read(self.user).status_code, 200)
                    continue
                set_client_state(self.user, state, seed=1)
                projection = get_service_projection(self.user)
                status_code, has_purchase_data = expected[state]
                self.assertEqual(projection.service_status, status_code)
                if status_code == 'PENDING':
                    self.assertEqual(projection.request_status, state)
                    self.assertEqual(self.read(self.user).status_code, 404)  # Results stay hidden while pending.
                self.assertEqual(Profile.objects.filter(user=self.user, rut__isnull=False).exists(),
                                 has_purchase_data)
                # Only the latest generated service survives each change; no results leak across states.
                self.assertLessEqual(ServiceRequest.objects.filter(purchase__owner__django_user=self.user).count(), 1)
                self.assertFalse(Analysis.objects.filter(participant__user=self.user).exists())
        self.assertIsNotNone(normalize_rut(Profile.objects.get(user=self.user).rut))

    def test_state_change_never_touches_a_real_active_service(self):
        set_client_state(self.user, 'WAITING_SAMPLE')
        ServiceStatusLog.objects.filter(request__purchase__owner__django_user=self.user).update(comment=None)
        with self.assertRaises(ValueError):
            set_client_state(self.user, 'registrado')
        self.assertEqual(get_service_projection(self.user).request_status, 'WAITING_SAMPLE')

    def test_rejects_bad_counts_and_non_clients(self):
        for count in (0, 41):
            with self.subTest(count=count), self.assertRaises(ValueError):
                populate_client_results(self.user, count)
        analyst = User.objects.get(username='results-analyst')
        with self.assertRaises(ValueError):
            populate_client_results(analyst, 5)
