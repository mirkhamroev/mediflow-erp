from .views import HospitalViewSet, DepartmentViewSet, OrganizationViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'hospitals', HospitalViewSet, basename='hospital')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'organizations', OrganizationViewSet, basename='organization')


urlpatterns = router.urls