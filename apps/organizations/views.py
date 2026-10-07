from django.shortcuts import render
from .models import Organization, Hospital, Department
from .serializers import OrganizationSerializer, HospitalSerializer, DepartmentSerializer
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from apps.commons.mixins import AuditRetrieveMixin
from apps.commons.permissions import IsOwner
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied


# Create your views here.
class HospitalViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = Hospital.objects.prefetch_related('departments').all()
    serializer_class = HospitalSerializer

    def get_permissions(self):
        # You can customize permissions here if needed
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]  # Only authenticated users can modify hospitals
        return [AllowAny()]  # Anyone can view hospitals



class DepartmentViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer

    def get_permissions(self):
        # You can customize permissions here if needed
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]  # Only authenticated users can modify departments
        return [AllowAny()]  # Anyone can view departments


class OrganizationViewSet(AuditRetrieveMixin, viewsets.ModelViewSet):
    queryset = Organization.objects.prefetch_related('hospitals', 'hospitals__departments').all()
    serializer_class = OrganizationSerializer
    pagination_class = None  # Disable pagination for this viewset

    def get_permissions(self):
        # You can customize permissions here if needed
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]  # Only authenticated users can modify organizations
        return [AllowAny()]  # Anyone can view organizations


