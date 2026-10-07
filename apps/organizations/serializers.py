from rest_framework import serializers
from .models import Organization, Hospital, Department


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'hospital', 'name', 'code', 'description', 'head',
                  'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class HospitalSerializer(serializers.ModelSerializer):
    departments = DepartmentSerializer(many=True, read_only=True)

    class Meta:
        model = Hospital
        fields = ['id', 'organization', 'name', 'code', 'address', 'city',
                  'phone_number', 'email', 'departments', 'is_active',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class OrganizationSerializer(serializers.ModelSerializer):
    # Nested read-only relations replace the hand-built list()/retrieve()
    # overrides in the viewset (and their N+1 queries).
    hospitals = HospitalSerializer(many=True, read_only=True)

    class Meta:
        model = Organization
        fields = ['id', 'name', 'legal_name', 'tax_id', 'address', 'email',
                  'phone_number', 'logo', 'hospitals', 'is_active',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
