from django.contrib import admin
from .models import Patient, PatientAllergy, PatientMedicalHistory


class PatientAllergyInline(admin.TabularInline):
    model = PatientAllergy
    extra = 1


class PatientMedicalHistoryInline(admin.TabularInline):
    model = PatientMedicalHistory
    extra = 1


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['medical_record_number', 'first_name', 'last_name', 'dob', 'gender', 'status', 'created_at']
    search_fields = ['medical_record_number', 'first_name', 'last_name', 'phone_number']
    list_filter = ['status', 'gender', 'blood_type', 'organization', 'primary_hospital']
    readonly_fields = ['medical_record_number', 'created_at', 'updated_at']
    inlines = [PatientAllergyInline, PatientMedicalHistoryInline]


@admin.register(PatientAllergy)
class PatientAllergyAdmin(admin.ModelAdmin):
    list_display = ['patient', 'allergen', 'severity', 'reaction', 'identified_date']
    search_fields = ['patient__first_name', 'patient__last_name', 'allergen']
    list_filter = ['severity', 'identified_date']


@admin.register(PatientMedicalHistory)
class PatientMedicalHistoryAdmin(admin.ModelAdmin):
    list_display = ['patient', 'condition_name', 'diagnosis_date', 'is_chronic']
    search_fields = ['patient__first_name', 'patient__last_name', 'condition_name']
    list_filter = ['is_chronic']
