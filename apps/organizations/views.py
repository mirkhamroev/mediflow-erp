from django.shortcuts import render
from .models import Organization, Hospital, Department
from .serializers import OrganizationSerializer, HospitalSerializer, DepartmentSerializer
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from apps.commons.permissions import IsOwner
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied


# Create your views here.
class HospitalViewSet(viewsets.ModelViewSet):
    queryset = Hospital.objects.prefetch_related('departments').all()
    serializer_class = HospitalSerializer

    def get_permissions(self):
        # You can customize permissions here if needed
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]  # Only authenticated users can modify hospitals
        return [AllowAny()]  # Anyone can view hospitals



class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer

    def get_permissions(self):
        # You can customize permissions here if needed
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]  # Only authenticated users can modify departments
        return [AllowAny()]  # Anyone can view departments


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.prefetch_related('hospitals', 'hospitals__departments').all()
    serializer_class = OrganizationSerializer
    pagination_class = None  # Disable pagination for this viewset

    def get_permissions(self):
        # You can customize permissions here if needed
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]  # Only authenticated users can modify organizations
        return [AllowAny()]  # Anyone can view organizations

    def create(self, request, *args, **kwargs):
        # Ensure that the user is authenticated and has permission to create an organization
        if not request.user.is_authenticated:
            raise PermissionDenied("You must be logged in to create an organization.")
        return super().create(request, *args, **kwargs)
        

    def list(self, request, *args, **kwargs):
        # Override list to include related hospitals and departments
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        for org in data:
            org_instance = Organization.objects.get(id=org['id'])
            org['hospitals'] = HospitalSerializer(org_instance.hospitals.all(), many=True).data
            org['departments'] = DepartmentSerializer(Department.objects.filter(hospital__organization=org_instance), many=True).data
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        # Override retrieve to include related hospitals and departments
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        data['hospitals'] = HospitalSerializer(instance.hospitals.all(), many=True).data
        data['departments'] = DepartmentSerializer(Department.objects.filter(hospital__organization=instance), many=True).data
        return Response(data)

    def perform_update(self, serializer):
        # Ensure that only the owner can update the organization
        if self.request.user != serializer.instance.created_by:
            raise PermissionDenied("You do not have permission to update this organization.")
        serializer.save()

