from .views import (
    HospitalViewSet, DepartmentViewSet, OrganizationViewSet,
    StaffProfileViewSet, DoctorProfileViewSet, NurseProfileViewSet,
    WardViewSet, RoomViewSet, BedViewSet, OperatingRoomViewSet,
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'hospitals', HospitalViewSet, basename='hospital')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'organizations', OrganizationViewSet, basename='organization')
router.register(r'staff-profiles', StaffProfileViewSet, basename='staff-profile')
router.register(r'doctor-profiles', DoctorProfileViewSet, basename='doctor-profile')
router.register(r'nurse-profiles', NurseProfileViewSet, basename='nurse-profile')
router.register(r'wards', WardViewSet, basename='ward')
router.register(r'rooms', RoomViewSet, basename='room')
router.register(r'beds', BedViewSet, basename='bed')
router.register(r'operating-rooms', OperatingRoomViewSet, basename='operating-room')


urlpatterns = router.urls