from .models import Organization, Hospital, Department, StaffProfile, DoctorProfile, NurseProfile
from .serializers import (
    OrganizationSerializer, HospitalSerializer, DepartmentSerializer,
    StaffProfileSerializer, DoctorProfileSerializer, NurseProfileSerializer,
)
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny
from apps.commons.mixins import AuditRetrieveMixin
from apps.commons.permissions import IsHospitalAdmin


class HospitalViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = Hospital.objects.prefetch_related('departments').all()
    serializer_class = HospitalSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [AllowAny()]


class DepartmentViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [AllowAny()]


class OrganizationViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = Organization.objects.prefetch_related('hospitals', 'hospitals__departments').all()
    serializer_class = OrganizationSerializer
    pagination_class = None  # Disable pagination for this viewset

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [AllowAny()]


class StaffProfileViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = StaffProfile.objects.select_related('user', 'organization', 'hospital', 'department').all()
    serializer_class = StaffProfileSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [IsAuthenticated()]


class DoctorProfileViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = DoctorProfile.objects.select_related(
        'staff_profile__user', 'staff_profile__organization',
        'staff_profile__hospital', 'staff_profile__department',
    ).all()
    serializer_class = DoctorProfileSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [IsAuthenticated()]


class NurseProfileViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = NurseProfile.objects.select_related(
        'staff_profile__user', 'staff_profile__organization',
        'staff_profile__hospital', 'staff_profile__department',
    ).all()
    serializer_class = NurseProfileSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [IsAuthenticated()]



