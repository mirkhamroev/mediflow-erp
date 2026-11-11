from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.commons.mixins import AuditRetrieveMixin
from apps.commons.permissions import IsHospitalAdmin, IsClinicalStaff
from .models import Patient, PatientAllergy, PatientMedicalHistory
from .serializers import (
    PatientCreateUpdateSerializer,
    PatientClinicalSerializer,
    PatientDemographicSerializer,
    PatientPharmacistSerializer,
    PatientBillingSerializer,
    PatientAllergySerializer,
    PatientMedicalHistorySerializer,
)


class CanManagePatient(BasePermission):
    """
    Allows patient registration and demographic updates by Clinical Staff,
    Receptionists, and Administrators.
    """
    message = "You do not have permission to modify patient records."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if user.is_superuser or user.role in ['admin', 'super_admin', 'doctor', 'nurse', 'receptionist']:
            return True
        if hasattr(user, 'has_role'):
            return user.has_role('admin', 'super_admin', 'doctor', 'nurse', 'receptionist')
        return False


class CanViewAllergies(BasePermission):
    """
    Allergies can be viewed by Clinical Staff, Pharmacists (drug safety),
    and Administrators. Forbidden for Accountants and Receptionists.
    """
    message = "You do not have permission to view patient allergies."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if user.is_superuser or user.role in ['admin', 'super_admin', 'doctor', 'nurse', 'pharmacist']:
            return True
        if hasattr(user, 'has_role'):
            return user.has_role('admin', 'super_admin', 'doctor', 'nurse', 'pharmacist')
        return False


class CanViewMedicalHistory(BasePermission):
    """
    Medical histories can only be accessed by Clinical Staff and Administrators.
    Strictly forbidden for Receptionists, Pharmacists, and Accountants.
    """
    message = "You do not have permission to access patient medical histories."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if user.is_superuser or user.role in ['admin', 'super_admin', 'doctor', 'nurse']:
            return True
        if hasattr(user, 'has_role'):
            return user.has_role('admin', 'super_admin', 'doctor', 'nurse')
        return False


class PatientViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    """
    Patient Management ViewSet with:
    - Multi-tenant row-level scoping (`get_queryset`).
    - Role-tailored column-level masking (`get_serializer_class`).
    - Audit logging for detail retrievals (`AuditRetrieveMixin`).
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'gender', 'blood_type', 'organization', 'primary_hospital']
    search_fields = ['medical_record_number', 'first_name', 'last_name', 'phone_number', 'email']
    ordering_fields = ['last_name', 'first_name', 'dob', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.is_active):
            return Patient.objects.none()

        base_qs = Patient.objects.select_related('organization', 'primary_hospital').prefetch_related(
            'allergies', 'medical_histories'
        )

        if user.is_superuser or user.role in ['super_admin']:
            return base_qs.all()

        staff = getattr(user, 'staff_profile', None)
        if staff and staff.organization_id:
            return base_qs.filter(organization_id=staff.organization_id)

        return Patient.objects.none()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PatientCreateUpdateSerializer

        user = getattr(self.request, 'user', None)
        role = getattr(user, 'role', None) if user else None

        if user and (user.is_superuser or role in ['doctor', 'nurse', 'admin', 'super_admin']):
            return PatientClinicalSerializer
        elif role == 'pharmacist':
            return PatientPharmacistSerializer
        elif role == 'accountant':
            return PatientBillingSerializer

        # Default for Receptionists, Front-Desk, and General Staff
        return PatientDemographicSerializer

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsHospitalAdmin()]
        elif self.action in ['create', 'update', 'partial_update']:
            return [CanManagePatient()]
        return [IsAuthenticated()]


class PatientAllergyViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    """
    Patient Allergy ViewSet.
    Writable only by Clinical Staff and Administrators.
    Readable by Clinical Staff, Pharmacists, and Administrators.
    """
    serializer_class = PatientAllergySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['patient', 'severity', 'identified_date']
    search_fields = ['allergen', 'reaction', 'patient__first_name', 'patient__last_name']
    ordering_fields = ['identified_date', 'severity', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.is_active):
            return PatientAllergy.objects.none()

        base_qs = PatientAllergy.objects.select_related('patient')

        if user.is_superuser or user.role == 'super_admin':
            return base_qs.all()

        staff = getattr(user, 'staff_profile', None)
        if staff and staff.organization_id:
            return base_qs.filter(patient__organization_id=staff.organization_id)

        return PatientAllergy.objects.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsClinicalStaff()]
        return [CanViewAllergies()]


class PatientMedicalHistoryViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    """
    Patient Medical History ViewSet.
    Accessible only by Clinical Staff and Administrators.
    """
    serializer_class = PatientMedicalHistorySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['patient', 'is_chronic']
    search_fields = ['condition_name', 'notes', 'patient__first_name', 'patient__last_name']
    ordering_fields = ['diagnosis_date', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.is_active):
            return PatientMedicalHistory.objects.none()

        base_qs = PatientMedicalHistory.objects.select_related('patient')

        if user.is_superuser or user.role == 'super_admin':
            return base_qs.all()

        staff = getattr(user, 'staff_profile', None)
        if staff and staff.organization_id:
            return base_qs.filter(patient__organization_id=staff.organization_id)

        return PatientMedicalHistory.objects.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsClinicalStaff()]
        return [CanViewMedicalHistory()]
