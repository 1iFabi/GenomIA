from django.urls import path
from .diseases_views import DiseasesAPIView
from .patient_variants_views import PatientVariantsAPIView
from .snp_views import VariantesAPIView
from .ancestry_views import AncestryAPIView
from .indigenous_views import IndigenousPeoplesAPIView
from .traits_views import TraitsAPIView
from .biometrics_views import BiometricsAPIView
from .biomarkers_views import BiomarkersAPIView
from .pharmacogenetics_views import PharmacogeneticsAPIView
from .upload_views import UploadGeneticFileAPIView, DeleteGeneticFileAPIView, GetUserReportStatusAPIView

urlpatterns = [
    # Genética
    path('genetics/diseases/', DiseasesAPIView.as_view(), name='api_diseases'),
    path('genetics/patient-variants/<int:user_id>/', PatientVariantsAPIView.as_view(), name='api_patient_variants'),
    path('genetics/variantes/', VariantesAPIView.as_view(), name='api_variantes'),
    path('genetics/ancestry/', AncestryAPIView.as_view(), name='api_ancestry'),
    path('genetics/indigenous/', IndigenousPeoplesAPIView.as_view(), name='api_indigenous'),
    path('genetics/traits/', TraitsAPIView.as_view(), name='api_traits'),
    path('genetics/biometrics/', BiometricsAPIView.as_view(), name='api_biometrics'),
    path('genetics/biomarkers/', BiomarkersAPIView.as_view(), name='api_biomarkers'),
    path('genetics/pharmacogenetics/', PharmacogeneticsAPIView.as_view(), name='api_pharmacogenetics'),

    # Ingestión de archivos
    path('ingest/upload-genetic-file/', UploadGeneticFileAPIView.as_view(), name='api_upload_genetic_file'),
    path('ingest/delete-genetic-file/', DeleteGeneticFileAPIView.as_view(), name='api_delete_genetic_file'),
    path('ingest/user-report-status/<int:user_id>/', GetUserReportStatusAPIView.as_view(), name='api_user_report_status'),
]
