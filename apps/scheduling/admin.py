from django.contrib import admin
from .models import (
    DoctorSchedule,
    WorkingHours,
    ExceptionalWorkingDay,
    TimeOff,
    Appointment,
    OperatingRoomSchedule,
)


class WorkingHoursInline(admin.TabularInline):
    model = WorkingHours
    extra = 1


class ExceptionalWorkingDayInline(admin.TabularInline):
    model = ExceptionalWorkingDay
    extra = 1


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'hospital', 'department', 'slot_duration_minutes', 'is_active']
    list_filter = ['is_active', 'hospital', 'department']
    search_fields = ['doctor__staff_profile__user__full_name', 'hospital__name', 'department__name']
    inlines = [WorkingHoursInline, ExceptionalWorkingDayInline]


@admin.register(ExceptionalWorkingDay)
class ExceptionalWorkingDayAdmin(admin.ModelAdmin):
    list_display = ['doctor_schedule', 'date', 'start_time', 'end_time', 'is_working_day', 'reason']
    list_filter = ['is_working_day', 'date']
    search_fields = ['doctor_schedule__doctor__staff_profile__user__full_name', 'reason']


@admin.register(WorkingHours)
class WorkingHoursAdmin(admin.ModelAdmin):
    list_display = ['doctor_schedule', 'day_of_week', 'start_time', 'end_time', 'is_active']
    list_filter = ['day_of_week', 'is_active']


@admin.register(TimeOff)
class TimeOffAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'leave_type', 'status', 'start_datetime', 'end_datetime']
    list_filter = ['leave_type', 'status']
    search_fields = ['doctor__staff_profile__user__full_name', 'reason']


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'doctor', 'hospital', 'department', 'start_time', 'end_time', 'status', 'appointment_type']
    list_filter = ['status', 'appointment_type', 'hospital', 'department']
    search_fields = ['patient__first_name', 'patient__last_name', 'patient__medical_record_number', 'doctor__staff_profile__user__full_name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(OperatingRoomSchedule)
class OperatingRoomScheduleAdmin(admin.ModelAdmin):
    list_display = ['operating_room', 'procedure_name', 'lead_surgeon', 'patient', 'start_time', 'end_time', 'status']
    list_filter = ['status', 'operating_room__hospital']
    search_fields = ['procedure_name', 'operating_room__name', 'lead_surgeon__staff_profile__user__full_name', 'patient__first_name', 'patient__last_name']
    readonly_fields = ['created_at', 'updated_at']
