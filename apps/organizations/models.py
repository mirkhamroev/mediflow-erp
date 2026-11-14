from django.db import models
from apps.accounts.models import User
from apps.commons.mixins import AuditableModelMixin
import uuid
from decimal import Decimal

# Create your models here.

class Organization(AuditableModelMixin, models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255)
    tax_id = models.CharField(max_length=50, unique=True)
    address = models.TextField()
    email = models.EmailField(max_length=255)
    phone_number = models.CharField(max_length=20, unique=True)
    logo = models.ImageField(upload_to='organization_logos/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'
        ordering = ['name', 'created_at']

    def __str__(self):
        return self.name

class Hospital(AuditableModelMixin, models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='hospitals')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, unique=True)
    email = models.EmailField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Hospital'
        verbose_name_plural = 'Hospitals'
        ordering = ['name', 'created_at']

    def __str__(self):
        return self.name


class Department(AuditableModelMixin, models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255)
    # unique per hospital, not globally: two hospitals can both have an "ER" department
    code = models.CharField(max_length=50)
    description = models.TextField(null=True, blank=True)
    head = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='headed_departments')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
        ordering = ['name', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['hospital', 'code'], name='unique_department_code_per_hospital'),
        ]

    def __str__(self):
        return self.name


class StaffProfile(AuditableModelMixin, models.Model):
    class EmploymentStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        ON_LEAVE = 'on_leave', 'On Leave'
        RETIRED = 'retired', 'Retired'
        SUSPENDED = 'suspended', 'Suspended'
        TERMINATED = 'terminated', 'Terminated'
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='staff_profiles')
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='staff_profiles')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_profiles')
    # unique per organization (see UniqueConstraint below), not globally
    employee_id = models.CharField(max_length=50)
    employment_status = models.CharField(max_length=20, choices=EmploymentStatus.choices, default=EmploymentStatus.ACTIVE)
    hire_date = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Staff Profile'
        verbose_name_plural = 'Staff Profiles'
        ordering = ['user__full_name', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['organization', 'employee_id'], name='unique_employee_id_per_organization')
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        errors = {}
        if self.hospital_id and self.organization_id and self.hospital.organization_id != self.organization_id:
            errors['hospital'] = "Selected hospital does not belong to the specified organization."
        if self.department_id and self.hospital_id and self.department.hospital_id != self.hospital_id:
            errors['department'] = "Selected department does not belong to the specified hospital."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.user.full_name} - {self.employee_id}"


class DoctorProfile(AuditableModelMixin, models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    staff_profile = models.OneToOneField(StaffProfile, on_delete=models.CASCADE, related_name='doctor_profile')
    specialization = models.CharField(max_length=255)
    years_of_experience = models.PositiveIntegerField()
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2)
    is_available_for_consultation = models.BooleanField(default=True)
    license_number = models.CharField(max_length=50, unique=True)
    license_expiry_date = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Doctor Profile'
        verbose_name_plural = 'Doctor Profiles'
        ordering = ['staff_profile__user__full_name', 'created_at']

    def __str__(self):
        return f"Dr. {self.staff_profile.user.full_name} - {self.specialization}"


class NurseProfile(AuditableModelMixin, models.Model):
    class NursingShift(models.TextChoices):
        DAY = 'day', 'Day'
        NIGHT = 'night', 'Night'
        ROTATING = 'rotating', 'Rotating'
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    staff_profile = models.OneToOneField(StaffProfile, on_delete=models.CASCADE, related_name='nurse_profile')
    license_number = models.CharField(max_length=50, unique=True)
    license_expiry_date = models.DateField()
    nurse_level = models.CharField(max_length=50)  # e.g., RN, LPN, etc.
    shift = models.CharField(max_length=20, choices=NursingShift.choices)
    nursing_specialty = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Nurse Profile'
        verbose_name_plural = 'Nurse Profiles'
        ordering = ['staff_profile__user__full_name', 'created_at']

    def __str__(self):
        return f"Nurse {self.staff_profile.user.full_name}"


class Ward(AuditableModelMixin, models.Model):
    class WardType(models.TextChoices):
        GENERAL = 'general', 'General'
        ICU = 'icu', 'Intensive Care Unit (ICU)'
        CCU = 'ccu', 'Coronary Care Unit (CCU)'
        PEDIATRIC = 'pediatric', 'Pediatric'
        MATERNITY = 'maternity', 'Maternity'
        SURGICAL = 'surgical', 'Surgical'
        PSYCHIATRIC = 'psychiatric', 'Psychiatric'
        ISOLATION = 'isolation', 'Isolation'
        EMERGENCY = 'emergency', 'Emergency'

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='wards')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='wards')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50)
    ward_type = models.CharField(max_length=50, choices=WardType.choices, default=WardType.GENERAL)
    floor = models.SmallIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ward"
        verbose_name_plural = "Wards"
        ordering = ['hospital', 'floor', 'name']
        constraints = [
            models.UniqueConstraint(fields=['hospital', 'code'], name="unique_ward_code_per_hospital")
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.department_id and self.hospital_id and self.department.hospital_id != self.hospital_id:
            raise ValidationError({'department': "Selected department does not belong to the specified hospital."})

    def __str__(self):
        return f"{self.name} - Fl. {self.floor} ({self.hospital.name})"


class Room(AuditableModelMixin, models.Model):
    class RoomType(models.TextChoices):
        STANDARD = 'standard', 'Standard'
        SEMI_PRIVATE = 'semi_private', 'Semi-Private'
        PRIVATE = 'private', 'Private'
        ICU = 'icu', 'ICU'
        ISOLATION = 'isolation', 'Isolation'
        DELUXE = 'deluxe', 'Deluxe / Suite'

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name='rooms')
    room_number = models.CharField(max_length=50)
    room_type = models.CharField(max_length=50, choices=RoomType.choices, default=RoomType.STANDARD)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Room"
        verbose_name_plural = "Rooms"
        ordering = ['ward', 'room_number']
        constraints = [
            models.UniqueConstraint(fields=['ward', 'room_number'], name='unique_room_number_per_ward')
        ]

    def __str__(self):
        return f"Room {self.room_number} ({self.ward.name})"


class Bed(AuditableModelMixin, models.Model):
    class BedStatus(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        OCCUPIED = 'occupied', 'Occupied'
        RESERVED = 'reserved', 'Reserved'
        MAINTENANCE = 'maintenance', 'Under Maintenance'

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='beds')
    bed_number = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=BedStatus.choices, default=BedStatus.AVAILABLE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Bed'
        verbose_name_plural = 'Beds'
        ordering = ['room', 'bed_number']
        constraints = [
            models.UniqueConstraint(fields=['room', 'bed_number'], name='unique_bed_number_per_room')
        ]

    def __str__(self):
        return f"Bed {self.bed_number} - Room {self.room.room_number}"


class OperatingRoom(AuditableModelMixin, models.Model):
    class ORStatus(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        IN_USE = 'in_use', 'In Use'
        CLEANING = 'cleaning', 'Cleaning / Turnover'
        MAINTENANCE = 'maintenance', 'Under Maintenance'

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='operating_rooms')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, blank=True, null=True, related_name='operating_rooms')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50)
    specialty = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=ORStatus.choices, default=ORStatus.AVAILABLE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Operating Room'
        verbose_name_plural = 'Operating Rooms'
        ordering = ['hospital', 'name']
        constraints = [
            models.UniqueConstraint(fields=['hospital', 'code'], name='unique_operating_room_code_per_hospital')
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.department_id and self.hospital_id and self.department.hospital_id != self.hospital_id:
            raise ValidationError({'department': "Selected department does not belong to the specified hospital."})

    def __str__(self):
        return f"{self.name} ({self.hospital.name})"