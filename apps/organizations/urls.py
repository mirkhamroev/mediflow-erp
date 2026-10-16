from .views import (
    HospitalViewSet, DepartmentViewSet, OrganizationViewSet,
    StaffProfileViewSet, DoctorProfileViewSet, NurseProfileViewSet,
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'hospitals', HospitalViewSet, basename='hospital')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'organizations', OrganizationViewSet, basename='organization')
router.register(r'staff-profiles', StaffProfileViewSet, basename='staff-profile')
router.register(r'doctor-profiles', DoctorProfileViewSet, basename='doctor-profile')
router.register(r'nurse-profiles', NurseProfileViewSet, basename='nurse-profile')


urlpatterns = router.urls