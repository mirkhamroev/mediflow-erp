from rest_framework import serializers
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import (
    DoctorSchedule,
    WorkingHours,
    ExceptionalWorkingDay,
    TimeOff,
    Appointment,
    OperatingRoomSchedule,
)


class WorkingHoursSerializer(serializers.ModelSerializer):
    day_of_week_display = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = WorkingHours
        fields = [
            'id', 'doctor_schedule', 'day_of_week', 'day_of_week_display',
            'start_time', 'end_time', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        instance = WorkingHours(**attrs)
        if self.instance:
            instance.pk = self.instance.pk
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)
        return attrs


class ExceptionalWorkingDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExceptionalWorkingDay
        fields = [
            'id', 'doctor_schedule', 'date', 'start_time', 'end_time',
            'is_working_day', 'reason', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        instance = ExceptionalWorkingDay(**attrs)
        if self.instance:
            instance.pk = self.instance.pk
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)
        return attrs


class DoctorScheduleSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source='doctor.staff_profile.user.full_name', read_only=True)
    hospital_name = serializers.CharField(source='hospital.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    working_hours = WorkingHoursSerializer(many=True, read_only=True)
    exceptional_days = ExceptionalWorkingDaySerializer(many=True, read_only=True)

    class Meta:
        model = DoctorSchedule
        fields = [
            'id', 'doctor', 'doctor_name',
            'hospital', 'hospital_name',
            'department', 'department_name',
            'slot_duration_minutes', 'buffer_time_minutes',
            'is_active', 'working_hours', 'exceptional_days',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        instance = DoctorSchedule(**attrs)
        if self.instance:
            instance.pk = self.instance.pk
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)
        return attrs


class TimeOffSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source='doctor.staff_profile.user.full_name', read_only=True)
    leave_type_display = serializers.CharField(source='get_leave_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = TimeOff
        fields = [
            'id', 'doctor', 'doctor_name',
            'start_datetime', 'end_datetime',
            'leave_type', 'leave_type_display',
            'status', 'status_display',
            'reason', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        instance = TimeOff(**attrs)
        if self.instance:
            instance.pk = self.instance.pk
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)
        return attrs


class AppointmentSerializer(serializers.ModelSerializer):
    """
    Detailed read representation for appointments.
    """
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    patient_mrn = serializers.CharField(source='patient.medical_record_number', read_only=True)
    patient_phone = serializers.CharField(source='patient.phone_number', read_only=True)
    doctor_name = serializers.CharField(source='doctor.staff_profile.user.full_name', read_only=True)
    doctor_specialization = serializers.CharField(source='doctor.specialization', read_only=True)
    hospital_name = serializers.CharField(source='hospital.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    appointment_type_display = serializers.CharField(source='get_appointment_type_display', read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id', 'patient', 'patient_name', 'patient_mrn', 'patient_phone',
            'doctor', 'doctor_name', 'doctor_specialization',
            'hospital', 'hospital_name',
            'department', 'department_name',
            'start_time', 'end_time',
            'status', 'status_display',
            'appointment_type', 'appointment_type_display',
            'reason', 'notes', 'cancellation_reason',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AppointmentCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and modifying appointments with full conflict prevention.
    """
    class Meta:
        model = Appointment
        fields = [
            'id', 'patient', 'doctor', 'hospital', 'department',
            'start_time', 'end_time', 'status', 'appointment_type',
            'reason', 'notes', 'cancellation_reason',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        # Merge existing instance values with incoming attrs for partial updates
        data = {
            'patient_id': getattr(self.instance, 'patient_id', None),
            'doctor_id': getattr(self.instance, 'doctor_id', None),
            'hospital_id': getattr(self.instance, 'hospital_id', None),
            'department_id': getattr(self.instance, 'department_id', None),
            'start_time': getattr(self.instance, 'start_time', None),
            'end_time': getattr(self.instance, 'end_time', None),
            'status': getattr(self.instance, 'status', Appointment.Status.SCHEDULED),
        }
        for k, v in attrs.items():
            if hasattr(v, 'pk'):
                data[f"{k}_id"] = v.pk
            else:
                data[k] = v

        temp_instance = Appointment(**data)
        if self.instance:
            temp_instance.pk = self.instance.pk

        try:
            temp_instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)

        return attrs


class OperatingRoomRescheduleSerializer(serializers.Serializer):
    new_start_time = serializers.DateTimeField(required=True)
    new_end_time = serializers.DateTimeField(required=True)

    def validate(self, attrs):
        if attrs['new_end_time'] <= attrs['new_start_time']:
            raise serializers.ValidationError("new_end_time must be after new_start_time.")
        return attrs



class AppointmentRescheduleSerializer(serializers.Serializer):
    new_start_time = serializers.DateTimeField(required=True)
    new_end_time = serializers.DateTimeField(required=True)

    def validate(self, attrs):
        if attrs['new_end_time'] <= attrs['new_start_time']:
            raise serializers.ValidationError("new_end_time must be after new_start_time.")
        return attrs


class AppointmentCancelSerializer(serializers.Serializer):
    cancellation_reason = serializers.CharField(required=True, min_length=3)


class OperatingRoomScheduleSerializer(serializers.ModelSerializer):
    operating_room_name = serializers.CharField(source='operating_room.name', read_only=True)
    operating_room_code = serializers.CharField(source='operating_room.code', read_only=True)
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    patient_mrn = serializers.CharField(source='patient.medical_record_number', read_only=True)
    surgeon_name = serializers.CharField(source='lead_surgeon.staff_profile.user.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = OperatingRoomSchedule
        fields = [
            'id', 'operating_room', 'operating_room_name', 'operating_room_code',
            'patient', 'patient_name', 'patient_mrn',
            'lead_surgeon', 'surgeon_name',
            'procedure_name', 'start_time', 'end_time',
            'status', 'status_display', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        data = {
            'operating_room_id': getattr(self.instance, 'operating_room_id', None),
            'patient_id': getattr(self.instance, 'patient_id', None),
            'lead_surgeon_id': getattr(self.instance, 'lead_surgeon_id', None),
            'procedure_name': getattr(self.instance, 'procedure_name', None),
            'start_time': getattr(self.instance, 'start_time', None),
            'end_time': getattr(self.instance, 'end_time', None),
            'status': getattr(self.instance, 'status', OperatingRoomSchedule.Status.RESERVED),
        }
        for k, v in attrs.items():
            if hasattr(v, 'pk'):
                data[f"{k}_id"] = v.pk
            else:
                data[k] = v

        temp_instance = OperatingRoomSchedule(**data)
        if self.instance:
            temp_instance.pk = self.instance.pk

        try:
            temp_instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)

        return attrs


class OperatingRoomRescheduleSerializer(serializers.Serializer):
    new_start_time = serializers.DateTimeField(required=True)
    new_end_time = serializers.DateTimeField(required=True)

    def validate(self, attrs):
        if attrs['new_end_time'] <= attrs['new_start_time']:
            raise serializers.ValidationError("new_end_time must be after new_start_time.")
        return attrs

