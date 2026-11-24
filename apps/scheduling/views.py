from datetime import datetime, date, timedelta, time
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.commons.mixins import AuditRetrieveMixin
from apps.commons.permissions import IsHospitalAdmin, IsClinicalStaff
from apps.organizations.models import DoctorProfile, OperatingRoom
from .models import (
    DoctorSchedule,
    WorkingHours,
    ExceptionalWorkingDay,
    TimeOff,
    Appointment,
    OperatingRoomSchedule,
)
from .serializers import (
    DoctorScheduleSerializer,
    WorkingHoursSerializer,
    ExceptionalWorkingDaySerializer,
    TimeOffSerializer,
    AppointmentSerializer,
    AppointmentCreateUpdateSerializer,
    AppointmentRescheduleSerializer,
    AppointmentCancelSerializer,
    OperatingRoomScheduleSerializer,
    OperatingRoomRescheduleSerializer,
)


class CanManageAppointment(BasePermission):
    """
    Appointments can be booked or managed by Clinical Staff (Doctors, Nurses),
    Receptionists, and Administrators.
    """
    message = "You do not have permission to manage appointments."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if user.is_superuser or user.role in ['admin', 'super_admin', 'doctor', 'nurse', 'receptionist']:
            return True
        if hasattr(user, 'has_role'):
            return user.has_role('admin', 'super_admin', 'doctor', 'nurse', 'receptionist')
        return False


class CanRequestTimeOff(BasePermission):
    """
    Doctors can request time off for themselves; Hospital Admins can create for anyone.
    """
    message = "You do not have permission to submit time off requests."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if user.is_superuser or user.role in ['admin', 'super_admin', 'doctor']:
            return True
        if hasattr(user, 'has_role'):
            return user.has_role('admin', 'super_admin', 'doctor')
        return False


class DoctorScheduleViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    """
    Doctor Master Schedules ViewSet.
    """
    queryset = DoctorSchedule.objects.select_related(
        'doctor__staff_profile__user', 'hospital', 'department'
    ).prefetch_related('working_hours', 'exceptional_days').all()
    serializer_class = DoctorScheduleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['doctor', 'hospital', 'department', 'is_active']
    search_fields = ['doctor__staff_profile__user__full_name', 'hospital__name', 'department__name']
    ordering_fields = ['doctor', 'hospital', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.is_active):
            return DoctorSchedule.objects.none()

        base_qs = DoctorSchedule.objects.select_related(
            'doctor__staff_profile__user', 'hospital', 'department'
        ).prefetch_related('working_hours', 'exceptional_days')

        if user.is_superuser or user.role == 'super_admin':
            return base_qs.all()

        staff = getattr(user, 'staff_profile', None)
        if staff and staff.organization_id:
            return base_qs.filter(hospital__organization_id=staff.organization_id)

        return DoctorSchedule.objects.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [IsAuthenticated()]


class WorkingHoursViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    """
    Weekly Recurring Shifts ViewSet.
    """
    queryset = WorkingHours.objects.select_related(
        'doctor_schedule__doctor__staff_profile__user'
    ).all()
    serializer_class = WorkingHoursSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['doctor_schedule', 'day_of_week', 'is_active']
    ordering_fields = ['day_of_week', 'start_time', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.is_active):
            return WorkingHours.objects.none()

        base_qs = WorkingHours.objects.select_related(
            'doctor_schedule__doctor__staff_profile__user'
        )

        if user.is_superuser or user.role == 'super_admin':
            return base_qs.all()

        staff = getattr(user, 'staff_profile', None)
        if staff and staff.organization_id:
            return base_qs.filter(doctor_schedule__hospital__organization_id=staff.organization_id)

        return WorkingHours.objects.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [IsAuthenticated()]


class ExceptionalWorkingDayViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    """
    Exceptional Working Days / Overrides ViewSet (Task 5.1).
    """
    queryset = ExceptionalWorkingDay.objects.select_related(
        'doctor_schedule__doctor__staff_profile__user'
    ).all()
    serializer_class = ExceptionalWorkingDaySerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['doctor_schedule', 'date', 'is_working_day']
    ordering_fields = ['date', 'start_time', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.is_active):
            return ExceptionalWorkingDay.objects.none()

        base_qs = ExceptionalWorkingDay.objects.select_related(
            'doctor_schedule__doctor__staff_profile__user'
        )

        if user.is_superuser or user.role == 'super_admin':
            return base_qs.all()

        staff = getattr(user, 'staff_profile', None)
        if staff and staff.organization_id:
            return base_qs.filter(doctor_schedule__hospital__organization_id=staff.organization_id)

        return ExceptionalWorkingDay.objects.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [IsAuthenticated()]


class TimeOffViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    """
    Doctor Time-Off / Absence ViewSet.
    Includes approve and reject administrative actions.
    """
    queryset = TimeOff.objects.select_related('doctor__staff_profile__user').all()
    serializer_class = TimeOffSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['doctor', 'leave_type', 'status']
    search_fields = ['doctor__staff_profile__user__full_name', 'reason']
    ordering_fields = ['start_datetime', 'end_datetime', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.is_active):
            return TimeOff.objects.none()

        base_qs = TimeOff.objects.select_related('doctor__staff_profile__user')

        if user.is_superuser or user.role == 'super_admin':
            return base_qs.all()

        staff = getattr(user, 'staff_profile', None)
        if staff and staff.organization_id:
            return base_qs.filter(doctor__staff_profile__organization_id=staff.organization_id)

        return TimeOff.objects.none()

    def get_permissions(self):
        if self.action in ['approve', 'reject', 'destroy']:
            return [IsHospitalAdmin()]
        elif self.action in ['create', 'update', 'partial_update']:
            return [CanRequestTimeOff()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        time_off = self.get_object()
        time_off.status = TimeOff.Status.APPROVED
        time_off.save()
        serializer = self.get_serializer(time_off)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        time_off = self.get_object()
        time_off.status = TimeOff.Status.REJECTED
        time_off.save()
        serializer = self.get_serializer(time_off)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AppointmentViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    """
    Patient Appointment Operations ViewSet (Section 5.2 - 5.4).
    Supports booking, concurrency safety, conflict prevention,
    available slots calculation, and lifecycle state transitions.
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['doctor', 'patient', 'hospital', 'department', 'status', 'appointment_type']
    search_fields = [
        'patient__first_name', 'patient__last_name',
        'patient__medical_record_number', 'doctor__staff_profile__user__full_name',
        'reason',
    ]
    ordering_fields = ['start_time', 'end_time', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.is_active):
            return Appointment.objects.none()

        base_qs = Appointment.objects.select_related(
            'patient', 'doctor__staff_profile__user', 'hospital', 'department'
        )

        if user.is_superuser or user.role == 'super_admin':
            return base_qs.all()

        staff = getattr(user, 'staff_profile', None)
        if staff and staff.organization_id:
            return base_qs.filter(hospital__organization_id=staff.organization_id)

        return Appointment.objects.none()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AppointmentCreateUpdateSerializer
        elif self.action == 'reschedule':
            return AppointmentRescheduleSerializer
        elif self.action == 'cancel':
            return AppointmentCancelSerializer
        return AppointmentSerializer

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsHospitalAdmin()]
        elif self.action in ['create', 'update', 'partial_update', 'confirm', 'check_in', 'start', 'complete', 'cancel', 'no_show', 'reschedule']:
            return [CanManageAppointment()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        """
        Concurrency-safe appointment creation with doctor database lock (Section 0.6 & 5.4).
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        doctor = serializer.validated_data.get('doctor')
        with transaction.atomic():
            if doctor:
                DoctorProfile.objects.select_for_update().get(pk=doctor.pk)
            instance = serializer.save()

        headers = self.get_success_headers(serializer.data)
        return Response(AppointmentSerializer(instance).data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['get'], url_path='available-slots')
    def available_slots(self, request):
        """
        Calculate open consultation slots for a doctor on a specific date (Section 5.1).
        Subtracts booked appointments and approved time-off from working hours/exceptional days.
        """
        doctor_id = request.query_params.get('doctor')
        date_str = request.query_params.get('date')

        if not doctor_id or not date_str:
            return Response(
                {"error": "Both 'doctor' and 'date' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        schedules = DoctorSchedule.objects.filter(
            doctor_id=doctor_id, is_active=True
        ).prefetch_related('working_hours', 'exceptional_days')

        if not schedules.exists():
            return Response(
                {"error": "No active schedule found for this doctor."},
                status=status.HTTP_404_NOT_FOUND,
            )

        schedule = schedules.first()
        slot_duration = timedelta(minutes=schedule.slot_duration_minutes)
        buffer_time = timedelta(minutes=schedule.buffer_time_minutes)

        # 1. Determine shift intervals on target_date
        shifts = []
        exceptional_day = schedule.exceptional_days.filter(date=target_date).first()
        if exceptional_day:
            if not exceptional_day.is_working_day:
                return Response({
                    "doctor": doctor_id,
                    "date": str(target_date),
                    "slot_duration_minutes": schedule.slot_duration_minutes,
                    "available_slots": [],
                    "note": f"Scheduled off-day: {exceptional_day.reason or 'Not working'}",
                }, status=status.HTTP_200_OK)
            shifts.append((exceptional_day.start_time, exceptional_day.end_time))
        else:
            working_shifts = schedule.working_hours.filter(day_of_week=target_date.weekday(), is_active=True)
            for ws in working_shifts:
                shifts.append((ws.start_time, ws.end_time))

        if not shifts:
            return Response({
                "doctor": doctor_id,
                "date": str(target_date),
                "slot_duration_minutes": schedule.slot_duration_minutes,
                "available_slots": [],
            }, status=status.HTTP_200_OK)

        # 2. Get existing booked appointments on target_date
        day_start = timezone.make_aware(datetime.combine(target_date, time.min))
        day_end = timezone.make_aware(datetime.combine(target_date, time.max))

        booked_appointments = Appointment.objects.filter(
            doctor_id=doctor_id,
            start_time__lt=day_end,
            end_time__gt=day_start,
        ).exclude(status__in=[Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW])

        # 3. Get approved leaves
        approved_leaves = TimeOff.objects.filter(
            doctor_id=doctor_id,
            status=TimeOff.Status.APPROVED,
            start_datetime__lt=day_end,
            end_datetime__gt=day_start,
        )

        # 4. Generate candidate slots
        available_slots = []
        now = timezone.now()

        for shift_start_t, shift_end_t in shifts:
            current_start = timezone.make_aware(datetime.combine(target_date, shift_start_t))
            shift_end = timezone.make_aware(datetime.combine(target_date, shift_end_t))

            while current_start + slot_duration <= shift_end:
                current_end = current_start + slot_duration

                if current_start > now:
                    has_appt_conflict = booked_appointments.filter(
                        start_time__lt=current_end,
                        end_time__gt=current_start,
                    ).exists()

                    has_leave_conflict = approved_leaves.filter(
                        start_datetime__lt=current_end,
                        end_datetime__gt=current_start,
                    ).exists()

                    if not has_appt_conflict and not has_leave_conflict:
                        available_slots.append({
                            "start_time": current_start.isoformat(),
                            "end_time": current_end.isoformat(),
                            "start_display": current_start.strftime('%H:%M'),
                            "end_display": current_end.strftime('%H:%M'),
                        })

                current_start = current_end + buffer_time

        return Response({
            "doctor": doctor_id,
            "doctor_name": schedule.doctor.staff_profile.user.full_name,
            "date": str(target_date),
            "slot_duration_minutes": schedule.slot_duration_minutes,
            "available_slots": available_slots,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm(self, request, pk=None):
        appointment = self.get_object()
        if appointment.status != Appointment.Status.SCHEDULED:
            return Response(
                {"error": f"Cannot confirm appointment with status '{appointment.get_status_display()}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appointment.status = Appointment.Status.CONFIRMED
        appointment.save()
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='check-in')
    def check_in(self, request, pk=None):
        appointment = self.get_object()
        if appointment.status not in [Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED]:
            return Response(
                {"error": f"Cannot check in appointment with status '{appointment.get_status_display()}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appointment.status = Appointment.Status.CHECKED_IN
        appointment.save()
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='start')
    def start(self, request, pk=None):
        appointment = self.get_object()
        if appointment.status != Appointment.Status.CHECKED_IN:
            return Response(
                {"error": "Patient must be checked in before consultation can start."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appointment.status = Appointment.Status.IN_PROGRESS
        appointment.save()
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        appointment = self.get_object()
        if appointment.status != Appointment.Status.IN_PROGRESS:
            return Response(
                {"error": "Only in-progress consultations can be completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appointment.status = Appointment.Status.COMPLETED
        appointment.save()
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        appointment = self.get_object()
        if appointment.status in [Appointment.Status.COMPLETED, Appointment.Status.CANCELLED]:
            return Response(
                {"error": f"Cannot cancel appointment with status '{appointment.get_status_display()}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        appointment.status = Appointment.Status.CANCELLED
        appointment.cancellation_reason = serializer.validated_data['cancellation_reason']
        appointment.save()
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='no-show')
    def no_show(self, request, pk=None):
        appointment = self.get_object()
        if appointment.status in [Appointment.Status.COMPLETED, Appointment.Status.CANCELLED, Appointment.Status.IN_PROGRESS]:
            return Response(
                {"error": f"Cannot mark appointment with status '{appointment.get_status_display()}' as no-show."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appointment.status = Appointment.Status.NO_SHOW
        appointment.save()
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reschedule')
    def reschedule(self, request, pk=None):
        appointment = self.get_object()
        if appointment.status in [Appointment.Status.COMPLETED, Appointment.Status.CANCELLED]:
            return Response(
                {"error": f"Cannot reschedule appointment with status '{appointment.get_status_display()}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_start = serializer.validated_data['new_start_time']
        new_end = serializer.validated_data['new_end_time']

        with transaction.atomic():
            DoctorProfile.objects.select_for_update().get(pk=appointment.doctor_id)

            appointment.start_time = new_start
            appointment.end_time = new_end
            appointment.status = Appointment.Status.SCHEDULED

            try:
                appointment.clean()
            except DjangoValidationError as exc:
                return Response(
                    {"error": exc.message if hasattr(exc, 'message') else str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            appointment.save()

        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_200_OK)


class OperatingRoomScheduleViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    """
    Operating Room Reservation ViewSet (Section 5.5).
    """
    serializer_class = OperatingRoomScheduleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['operating_room', 'lead_surgeon', 'status']
    search_fields = [
        'procedure_name', 'operating_room__name',
        'lead_surgeon__staff_profile__user__full_name', 'patient__first_name', 'patient__last_name',
    ]
    ordering_fields = ['start_time', 'end_time', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.is_active):
            return OperatingRoomSchedule.objects.none()

        base_qs = OperatingRoomSchedule.objects.select_related(
            'operating_room', 'patient', 'lead_surgeon__staff_profile__user'
        )

        if user.is_superuser or user.role == 'super_admin':
            return base_qs.all()

        staff = getattr(user, 'staff_profile', None)
        if staff and staff.organization_id:
            return base_qs.filter(operating_room__hospital__organization_id=staff.organization_id)

        return OperatingRoomSchedule.objects.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'cancel', 'reschedule']:
            return [IsClinicalStaff()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        """
        Concurrency-safe theater reservation with OR suite lock.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        or_room = serializer.validated_data.get('operating_room')
        with transaction.atomic():
            if or_room:
                OperatingRoom.objects.select_for_update().get(pk=or_room.pk)
            instance = serializer.save()

        headers = self.get_success_headers(serializer.data)
        return Response(OperatingRoomScheduleSerializer(instance).data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        schedule = self.get_object()
        schedule.status = OperatingRoomSchedule.Status.CANCELLED
        schedule.save()
        return Response(self.get_serializer(schedule).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reschedule')
    def reschedule(self, request, pk=None):
        schedule = self.get_object()
        if schedule.status in [OperatingRoomSchedule.Status.COMPLETED, OperatingRoomSchedule.Status.CANCELLED]:
            return Response(
                {"error": f"Cannot reschedule surgery with status '{schedule.get_status_display()}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OperatingRoomRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_start = serializer.validated_data['new_start_time']
        new_end = serializer.validated_data['new_end_time']

        with transaction.atomic():
            OperatingRoom.objects.select_for_update().get(pk=schedule.operating_room_id)

            schedule.start_time = new_start
            schedule.end_time = new_end
            schedule.status = OperatingRoomSchedule.Status.RESERVED

            try:
                schedule.clean()
            except DjangoValidationError as exc:
                return Response(
                    {"error": exc.message if hasattr(exc, 'message') else str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            schedule.save()

        return Response(OperatingRoomScheduleSerializer(schedule).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='availability')
    def availability(self, request):
        """
        Track Operating Room booked intervals and availability for a given date (Task 5.5).
        """
        or_id = request.query_params.get('operating_room')
        date_str = request.query_params.get('date')

        if not or_id or not date_str:
            return Response(
                {"error": "Both 'operating_room' and 'date' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        day_start = timezone.make_aware(datetime.combine(target_date, time.min))
        day_end = timezone.make_aware(datetime.combine(target_date, time.max))

        booked_surgeries = OperatingRoomSchedule.objects.filter(
            operating_room_id=or_id,
            start_time__lt=day_end,
            end_time__gt=day_start,
        ).exclude(status=OperatingRoomSchedule.Status.CANCELLED).order_by('start_time')

        booked_intervals = [
            {
                "id": str(s.id),
                "procedure_name": s.procedure_name,
                "surgeon_name": s.lead_surgeon.staff_profile.user.full_name,
                "start_time": s.start_time.isoformat(),
                "end_time": s.end_time.isoformat(),
                "start_display": s.start_time.strftime('%H:%M'),
                "end_display": s.end_time.strftime('%H:%M'),
                "status": s.status,
            }
            for s in booked_surgeries
        ]

        return Response({
            "operating_room": or_id,
            "date": str(target_date),
            "booked_surgeries": booked_intervals,
            "total_booked_surgeries": len(booked_intervals),
        }, status=status.HTTP_200_OK)
