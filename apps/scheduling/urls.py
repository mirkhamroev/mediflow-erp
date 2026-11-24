from rest_framework.routers import DefaultRouter
from .views import (
    DoctorScheduleViewSet,
    WorkingHoursViewSet,
    ExceptionalWorkingDayViewSet,
    TimeOffViewSet,
    AppointmentViewSet,
    OperatingRoomScheduleViewSet,
)

router = DefaultRouter()
router.register(r'doctor-schedules', DoctorScheduleViewSet, basename='doctor-schedule')
router.register(r'working-hours', WorkingHoursViewSet, basename='working-hours')
router.register(r'exceptional-working-days', ExceptionalWorkingDayViewSet, basename='exceptional-working-day')
router.register(r'time-offs', TimeOffViewSet, basename='time-off')
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'operating-room-schedules', OperatingRoomScheduleViewSet, basename='operating-room-schedule')

urlpatterns = router.urls

