from rest_framework.routers import DefaultRouter
from .views import (
    PatientViewSet,
    PatientAllergyViewSet,
    PatientMedicalHistoryViewSet,
)

router = DefaultRouter()
router.register(r'patients', PatientViewSet, basename='patient')
router.register(r'allergies', PatientAllergyViewSet, basename='patient-allergy')
router.register(r'medical-histories', PatientMedicalHistoryViewSet, basename='patient-medical-history')

urlpatterns = router.urls
