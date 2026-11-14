import uuid
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.commons.mixins import AuditableModelMixin
from apps.organizations.models import DoctorProfile, Hospital, Department, OperatingRoom
from apps.clinical.models import Patient


class DoctorSchedule(AuditableModelMixin, models.Model):
    """
    Master scheduling profile configuring a doctor's availability at a specific hospital/department.
    """
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name='schedules',
    )
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        related_name='doctor_schedules',
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='doctor_schedules',
    )
    slot_duration_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Standard consultation slot duration in minutes.",
    )
    buffer_time_minutes = models.PositiveIntegerField(
        default=5,
        help_text="Buffer time between consultation slots in minutes.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Doctor Schedule'
        verbose_name_plural = 'Doctor Schedules'
        ordering = ['doctor', 'hospital']
        constraints = [
            models.UniqueConstraint(
                fields=['doctor', 'hospital', 'department'],
                name='unique_schedule_per_doctor_hospital_department',
            )
        ]

    def clean(self):
        if self.department_id and self.hospital_id and self.department.hospital_id != self.hospital_id:
            raise ValidationError({
                'department': "Selected department does not belong to the specified hospital."
            })
        if self.doctor_id and self.hospital_id:
            staff_hospital_id = self.doctor.staff_profile.hospital_id
            if staff_hospital_id != self.hospital_id:
                raise ValidationError({
                    'hospital': "Doctor is not assigned to this hospital."
                })

    def __str__(self):
        return f"Schedule: Dr. {self.doctor.staff_profile.user.full_name} ({self.hospital.name})"


class WorkingHours(AuditableModelMixin, models.Model):
    """
    Weekly recurring availability slots for a doctor's schedule.
    """
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    doctor_schedule = models.ForeignKey(
        DoctorSchedule,
        on_delete=models.CASCADE,
        related_name='working_hours',
    )
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    start_time = models.TimeField(help_text="Shift start time (HH:MM)")
    end_time = models.TimeField(help_text="Shift end time (HH:MM)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Working Hours'
        verbose_name_plural = 'Working Hours'
        ordering = ['day_of_week', 'start_time']
        constraints = [
            models.UniqueConstraint(
                fields=['doctor_schedule', 'day_of_week', 'start_time'],
                name='unique_working_hours_slot',
            )
        ]

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({'end_time': "Shift end time must be after start time."})

        # Overlapping shifts check on the same schedule and day
        if self.doctor_schedule_id and self.day_of_week is not None and self.start_time and self.end_time:
            overlapping = WorkingHours.objects.filter(
                doctor_schedule_id=self.doctor_schedule_id,
                day_of_week=self.day_of_week,
                is_active=True,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            )
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError("This shift overlaps with an existing active shift on this day.")

    def __str__(self):
        return f"{self.get_day_of_week_display()}: {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"


class ExceptionalWorkingDay(AuditableModelMixin, models.Model):
    """
    Date-specific schedule override (Task 5.1).
    Used for on-call days, holiday shifts, or special off-days.
    """
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    doctor_schedule = models.ForeignKey(
        DoctorSchedule,
        on_delete=models.CASCADE,
        related_name='exceptional_days',
    )
    date = models.DateField(help_text="Calendar date of the exceptional schedule.")
    start_time = models.TimeField(null=True, blank=True, help_text="Override shift start time")
    end_time = models.TimeField(null=True, blank=True, help_text="Override shift end time")
    is_working_day = models.BooleanField(
        default=True,
        help_text="True if doctor works on this date; False if overriding a regular working day to be off.",
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="e.g. Holiday on-call shift, Clinic closed for renovation",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Exceptional Working Day'
        verbose_name_plural = 'Exceptional Working Days'
        ordering = ['date', 'start_time']

    def clean(self):
        if self.is_working_day:
            if not self.start_time or not self.end_time:
                raise ValidationError("Start time and end time are required for working days.")
            if self.end_time <= self.start_time:
                raise ValidationError({'end_time': "Shift end time must be after start time."})

            if self.doctor_schedule_id and self.date:
                overlapping = ExceptionalWorkingDay.objects.filter(
                    doctor_schedule_id=self.doctor_schedule_id,
                    date=self.date,
                    is_working_day=True,
                    start_time__lt=self.end_time,
                    end_time__gt=self.start_time,
                )
                if self.pk:
                    overlapping = overlapping.exclude(pk=self.pk)
                if overlapping.exists():
                    raise ValidationError("This exceptional shift overlaps with another shift on the same date.")

    def __str__(self):
        if not self.is_working_day:
            return f"{self.date} (Off-day override)"
        return f"{self.date}: {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"


class TimeOff(AuditableModelMixin, models.Model):
    """
    Doctor leaves and unavailability intervals (vacations, sick leaves, conferences).
    """
    class LeaveType(models.TextChoices):
        VACATION = 'vacation', 'Vacation'
        SICK_LEAVE = 'sick_leave', 'Sick Leave'
        CONFERENCE = 'conference', 'Conference / Training'
        EMERGENCY = 'emergency', 'Emergency Leave'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Approval'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name='time_offs',
    )
    start_datetime = models.DateTimeField(help_text="Start date and time of leave")
    end_datetime = models.DateTimeField(help_text="End date and time of leave")
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices, default=LeaveType.VACATION)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Time Off'
        verbose_name_plural = 'Time Offs'
        ordering = ['-start_datetime']

    def clean(self):
        if self.start_datetime and self.end_datetime and self.end_datetime <= self.start_datetime:
            raise ValidationError({'end_datetime': "Leave end datetime must be after start datetime."})

    def __str__(self):
        return f"Dr. {self.doctor.staff_profile.user.full_name} Leave ({self.start_datetime.strftime('%Y-%m-%d')} - {self.end_datetime.strftime('%Y-%m-%d')})"


class Appointment(AuditableModelMixin, models.Model):
    """
    Patient Outpatient Consultation Appointment.
    Includes lifecycle tracking and double-booking conflict prevention.
    """
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        CONFIRMED = 'confirmed', 'Confirmed'
        CHECKED_IN = 'checked_in', 'Checked In'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        NO_SHOW = 'no_show', 'No Show'

    class AppointmentType(models.TextChoices):
        ROUTINE = 'routine', 'Routine Consultation'
        FOLLOW_UP = 'follow_up', 'Follow-Up'
        EMERGENCY = 'emergency', 'Emergency'
        TELECONSULTATION = 'teleconsultation', 'Teleconsultation'

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='appointments',
    )
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name='appointments',
    )
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        related_name='appointments',
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='appointments',
    )
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
        db_index=True,
    )
    appointment_type = models.CharField(
        max_length=20,
        choices=AppointmentType.choices,
        default=AppointmentType.ROUTINE,
    )
    reason = models.CharField(max_length=255, help_text="Primary reason for visit")
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Appointment'
        verbose_name_plural = 'Appointments'
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['doctor', 'start_time']),
            models.Index(fields=['patient', 'start_time']),
            models.Index(fields=['hospital', 'status']),
        ]

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({'end_time': "Appointment end time must be after start time."})

        if self.department_id and self.hospital_id and self.department.hospital_id != self.hospital_id:
            raise ValidationError({'department': "Selected department does not belong to the specified hospital."})

        # Section 5.4 Conflict Prevention (Double-booking check)
        if self.doctor_id and self.start_time and self.end_time:
            # Active appointments excluding cancelled/no-show
            overlapping = Appointment.objects.filter(
                doctor_id=self.doctor_id,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            ).exclude(
                status__in=[self.Status.CANCELLED, self.Status.NO_SHOW]
            )
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)

            if overlapping.exists():
                conflict = overlapping.first()
                raise ValidationError(
                    f"Conflict: Dr. {self.doctor.staff_profile.user.full_name} already has an active appointment "
                    f"from {conflict.start_time.strftime('%H:%M')} to {conflict.end_time.strftime('%H:%M')}."
                )

            # Check Doctor TimeOff (Approved leaves block appointments)
            time_off_conflicts = TimeOff.objects.filter(
                doctor_id=self.doctor_id,
                status=TimeOff.Status.APPROVED,
                start_datetime__lt=self.end_time,
                end_datetime__gt=self.start_time,
            )
            if time_off_conflicts.exists():
                leave = time_off_conflicts.first()
                raise ValidationError(
                    f"Unavailable: Dr. {self.doctor.staff_profile.user.full_name} is on approved {leave.get_leave_type_display()}."
                )

            # Check Doctor Working Hours & Exceptional Days if schedule exists
            schedules = DoctorSchedule.objects.filter(
                doctor_id=self.doctor_id,
                hospital_id=self.hospital_id,
                is_active=True,
            )
            if schedules.exists():
                schedule = schedules.first()
                appt_date = self.start_time.date()
                appt_start_time = self.start_time.time()
                appt_end_time = self.end_time.time()

                # Check exceptional working days first (date-specific override)
                exceptional_days = ExceptionalWorkingDay.objects.filter(
                    doctor_schedule=schedule,
                    date=appt_date,
                )
                if exceptional_days.exists():
                    exp = exceptional_days.first()
                    if not exp.is_working_day:
                        raise ValidationError(
                            f"Unavailable: Dr. {self.doctor.staff_profile.user.full_name} is not available on {appt_date} (scheduled off-day override)."
                        )
                    if not (appt_start_time >= exp.start_time and appt_end_time <= exp.end_time):
                        raise ValidationError(
                            f"Appointment is outside exceptional shift hours ({exp.start_time.strftime('%H:%M')} - {exp.end_time.strftime('%H:%M')})."
                        )
                else:
                    # Check recurring weekly working hours
                    has_configured_shifts = WorkingHours.objects.filter(
                        doctor_schedule=schedule,
                        is_active=True,
                    ).exists()
                    if has_configured_shifts:
                        shifts = WorkingHours.objects.filter(
                            doctor_schedule=schedule,
                            day_of_week=appt_date.weekday(),
                            is_active=True,
                        )
                        if not shifts.exists():
                            raise ValidationError(
                                f"Dr. {self.doctor.staff_profile.user.full_name} does not have scheduled working hours on {self.start_time.strftime('%A')}."
                            )
                        in_any_shift = any(
                            appt_start_time >= s.start_time and appt_end_time <= s.end_time
                            for s in shifts
                        )
                        if not in_any_shift:
                            raise ValidationError(
                                f"Appointment is outside Dr. {self.doctor.staff_profile.user.full_name}'s scheduled working hours for {self.start_time.strftime('%A')}."
                            )

    def __str__(self):
        return f"{self.patient.full_name} with Dr. {self.doctor.staff_profile.user.full_name} ({self.start_time.strftime('%Y-%m-%d %H:%M')})"


class OperatingRoomSchedule(AuditableModelMixin, models.Model):
    """
    Surgical Theater reservation scheduling.
    Prevents overlapping operations in the same operating room suite.
    """
    class Status(models.TextChoices):
        RESERVED = 'reserved', 'Reserved'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        DELAYED = 'delayed', 'Delayed'

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    operating_room = models.ForeignKey(
        OperatingRoom,
        on_delete=models.CASCADE,
        related_name='schedules',
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='surgical_schedules',
    )
    lead_surgeon = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name='surgeries',
    )
    procedure_name = models.CharField(max_length=255, help_text="e.g. Coronary Artery Bypass, Appendectomy")
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RESERVED,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Operating Room Schedule'
        verbose_name_plural = 'Operating Room Schedules'
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['operating_room', 'start_time']),
            models.Index(fields=['lead_surgeon', 'start_time']),
        ]

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({'end_time': "Surgical schedule end time must be after start time."})

        # OR Double-booking conflict check
        if self.operating_room_id and self.start_time and self.end_time:
            overlapping_or = OperatingRoomSchedule.objects.filter(
                operating_room_id=self.operating_room_id,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            ).exclude(status=self.Status.CANCELLED)

            if self.pk:
                overlapping_or = overlapping_or.exclude(pk=self.pk)

            if overlapping_or.exists():
                conflict = overlapping_or.first()
                raise ValidationError(
                    f"Conflict: Operating Room {self.operating_room.name} is already reserved for "
                    f"'{conflict.procedure_name}' from {conflict.start_time.strftime('%H:%M')} to {conflict.end_time.strftime('%H:%M')}."
                )

            # Lead surgeon double-booking check
            overlapping_surgeon = OperatingRoomSchedule.objects.filter(
                lead_surgeon_id=self.lead_surgeon_id,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            ).exclude(status=self.Status.CANCELLED)

            if self.pk:
                overlapping_surgeon = overlapping_surgeon.exclude(pk=self.pk)

            if overlapping_surgeon.exists():
                conflict = overlapping_surgeon.first()
                raise ValidationError(
                    f"Conflict: Lead Surgeon Dr. {self.lead_surgeon.staff_profile.user.full_name} is already booked for "
                    f"'{conflict.procedure_name}' during this time window."
                )

    def __str__(self):
        return f"{self.procedure_name} in {self.operating_room.name} ({self.start_time.strftime('%Y-%m-%d %H:%M')})"
