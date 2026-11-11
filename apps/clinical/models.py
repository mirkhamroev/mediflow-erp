import uuid
from datetime import date
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.commons.mixins import AuditableModelMixin
from apps.organizations.models import Organization, Hospital


def validate_dob(value):
    if value and value > date.today():
        raise ValidationError("The birth date cannot be in the future!")


class Patient(AuditableModelMixin, models.Model):
    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'
        OTHER = 'other', 'Other'
        UNKNOWN = 'unknown', 'Unknown'

    class BloodType(models.TextChoices):
        A_POS = 'A+', 'A+'
        A_NEG = 'A-', 'A-'
        B_POS = 'B+', 'B+'
        B_NEG = 'B-', 'B-'
        AB_POS = 'AB+', 'AB+'
        AB_NEG = 'AB-', 'AB-'
        O_POS = 'O+', 'O+'
        O_NEG = 'O-', 'O-'
        RARE = 'rare', 'Rare Phenotype'
        UNKNOWN = 'unknown', 'Unknown'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        DECEASED = 'deceased', 'Deceased'

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    medical_record_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Unique Medical Record Number (MRN)",
    )
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    dob = models.DateField(validators=[validate_dob], help_text="Format: YYYY-MM-DD")
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.UNKNOWN)
    blood_type = models.CharField(max_length=10, choices=BloodType.choices, default=BloodType.UNKNOWN)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)

    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    emergency_contact_relation = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='patients',
    )
    primary_hospital = models.ForeignKey(
        Hospital,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='primary_patients',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Patient'
        verbose_name_plural = 'Patients'
        ordering = ['last_name', 'first_name', 'created_at']
        indexes = [
            models.Index(fields=['medical_record_number']),
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['phone_number']),
        ]

    def clean(self):
        if self.primary_hospital and self.organization:
            if self.primary_hospital.organization_id != self.organization_id:
                raise ValidationError({
                    'primary_hospital': "Primary hospital does not belong to the selected organization."
                })

    def save(self, *args, **kwargs):
        # Auto-generate MRN if not set: MRN-YYYY-XXXXXX
        if not self.medical_record_number:
            self.medical_record_number = self.generate_mrn()
        super().save(*args, **kwargs)

    @classmethod
    def generate_mrn(cls):
        year = timezone.now().strftime('%Y')
        random_suffix = uuid.uuid4().hex[:6].upper()
        mrn = f"MRN-{year}-{random_suffix}"
        while cls.objects.filter(medical_record_number=mrn).exists():
            random_suffix = uuid.uuid4().hex[:6].upper()
            mrn = f"MRN-{year}-{random_suffix}"
        return mrn

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return f"{self.full_name} ({self.medical_record_number})"


class PatientAllergy(AuditableModelMixin, models.Model):
    class Severity(models.TextChoices):
        MILD = 'mild', 'Mild'
        MODERATE = 'moderate', 'Moderate'
        SEVERE = 'severe', 'Severe'
        LIFE_THREATENING = 'life_threatening', 'Life Threatening'

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='allergies')
    allergen = models.CharField(max_length=255, help_text="e.g. Penicillin, Peanuts, Latex")
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MODERATE)
    reaction = models.CharField(max_length=255, blank=True, help_text="e.g. Anaphylaxis, Rash, Swelling")
    identified_date = models.DateField(default=date.today)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Patient Allergy'
        verbose_name_plural = 'Patient Allergies'
        ordering = ['-identified_date', 'allergen']

    def __str__(self):
        return f"{self.patient.full_name} - {self.allergen} ({self.get_severity_display()})"


class PatientMedicalHistory(AuditableModelMixin, models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='medical_histories')
    condition_name = models.CharField(max_length=255, help_text="e.g. Type 2 Diabetes, Hypertension, Asthma")
    diagnosis_date = models.DateField(null=True, blank=True)
    is_chronic = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Patient Medical History'
        verbose_name_plural = 'Patient Medical Histories'
        ordering = ['-diagnosis_date', 'condition_name']

    def __str__(self):
        return f"{self.patient.full_name} - {self.condition_name}"
