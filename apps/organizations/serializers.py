from rest_framework import serializers
from .models import Organization, Hospital, Department, StaffProfile, DoctorProfile, NurseProfile


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


class StaffProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = StaffProfile
        fields = [
            'id', 'user', 'user_email', 'user_full_name',
            'organization', 'hospital', 'department',
            'employee_id', 'employment_status', 'hire_date',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        organization = attrs.get('organization') or getattr(self.instance, 'organization', None)
        hospital = attrs.get('hospital') or getattr(self.instance, 'hospital', None)
        department = attrs.get('department', getattr(self.instance, 'department', None))

        errors = {}
        if hospital and organization and hospital.organization_id != organization.id:
            errors['hospital'] = "Selected hospital does not belong to the specified organization."
        if department and hospital and department.hospital_id != hospital.id:
            errors['department'] = "Selected department does not belong to the specified hospital."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class DoctorProfileSerializer(serializers.ModelSerializer):
    staff_details = StaffProfileSerializer(source='staff_profile', read_only=True)

    class Meta:
        model = DoctorProfile
        fields = [
            'id', 'staff_profile', 'staff_details',
            'specialization', 'years_of_experience', 'consultation_fee',
            'is_available_for_consultation', 'license_number', 'license_expiry_date',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NurseProfileSerializer(serializers.ModelSerializer):
    staff_details = StaffProfileSerializer(source='staff_profile', read_only=True)

    class Meta:
        model = NurseProfile
        fields = [
            'id', 'staff_profile', 'staff_details',
            'license_number', 'license_expiry_date', 'nurse_level',
            'shift', 'nursing_specialty', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

