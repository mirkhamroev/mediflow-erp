from .models import (
    Organization, Hospital, Department, StaffProfile, DoctorProfile, NurseProfile,
    Ward, Room, Bed, OperatingRoom,
)
from .serializers import (
    OrganizationSerializer, HospitalSerializer, DepartmentSerializer,
    StaffProfileSerializer, DoctorProfileSerializer, NurseProfileSerializer,
    WardSerializer, RoomSerializer, BedSerializer, OperatingRoomSerializer,
)
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
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


class WardViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = Ward.objects.select_related('hospital', 'department').all()
    serializer_class = WardSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['hospital', 'department', 'ward_type', 'is_active', 'floor']
    search_fields = ['name', 'code', 'hospital__name']
    ordering_fields = ['floor', 'name', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [IsAuthenticated()]


class RoomViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = Room.objects.select_related('ward__hospital').prefetch_related('beds').all()
    serializer_class = RoomSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ward', 'ward__hospital', 'room_type', 'is_active']
    search_fields = ['room_number', 'ward__name']
    ordering_fields = ['room_number', 'daily_rate', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [IsAuthenticated()]


class BedViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = Bed.objects.select_related('room__ward__hospital').all()
    serializer_class = BedSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['room', 'room__ward', 'room__ward__hospital', 'status', 'is_active']
    search_fields = ['bed_number', 'room__room_number', 'room__ward__name']
    ordering_fields = ['bed_number', 'status', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [IsAuthenticated()]


class OperatingRoomViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = OperatingRoom.objects.select_related('hospital', 'department').all()
    serializer_class = OperatingRoomSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['hospital', 'department', 'status', 'is_active']
    search_fields = ['name', 'code', 'specialty']
    ordering_fields = ['name', 'code', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsHospitalAdmin()]
        return [IsAuthenticated()]




