from rest_framework import serializers
from .models import Patient, PatientAllergy, PatientMedicalHistory


class PatientAllergySerializer(serializers.ModelSerializer):
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)

    class Meta:
        model = PatientAllergy
        fields = [
            'id', 'patient', 'allergen', 'severity', 'severity_display',
            'reaction', 'identified_date', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PatientMedicalHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientMedicalHistory
        fields = [
            'id', 'patient', 'condition_name', 'diagnosis_date',
            'is_chronic', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PatientCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = [
            'id', 'medical_record_number',
            'first_name', 'last_name', 'dob', 'gender', 'blood_type',
            'phone_number', 'email', 'address', 'city',
            'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relation',
            'status', 'organization', 'primary_hospital',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'medical_record_number', 'created_at', 'updated_at']

    def validate(self, attrs):
        organization = attrs.get('organization') or getattr(self.instance, 'organization', None)
        primary_hospital = attrs.get('primary_hospital') or getattr(self.instance, 'primary_hospital', None)

        if primary_hospital and organization and primary_hospital.organization_id != organization.id:
            raise serializers.ValidationError({
                'primary_hospital': "Primary hospital does not belong to the selected organization."
            })

        # Section 4.2 Duplicate Patient Detection (Name + DOB + Phone)
        if not self.instance:  # On creation
            first_name = attrs.get('first_name', '').strip()
            last_name = attrs.get('last_name', '').strip()
            dob = attrs.get('dob')
            phone_number = attrs.get('phone_number', '').strip()

            duplicate = Patient.objects.filter(
                first_name__iexact=first_name,
                last_name__iexact=last_name,
                dob=dob,
                phone_number=phone_number,
            )
            if organization:
                duplicate = duplicate.filter(organization=organization)

            if duplicate.exists():
                existing = duplicate.first()
                raise serializers.ValidationError(
                    f"Duplicate patient detected: A patient with this name, date of birth, and phone number "
                    f"is already registered (MRN: {existing.medical_record_number})."
                )

        return attrs


class PatientClinicalSerializer(serializers.ModelSerializer):
    """
    Full clinical representation for Doctors, Nurses, and Medical Administrators.
    Exposes complete allergies, medical history, blood type, and emergency contacts.
    """
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    blood_type_display = serializers.CharField(source='get_blood_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    primary_hospital_name = serializers.CharField(source='primary_hospital.name', read_only=True)
    allergies = PatientAllergySerializer(many=True, read_only=True)
    medical_histories = PatientMedicalHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Patient
        fields = [
            'id', 'medical_record_number', 'first_name', 'last_name', 'full_name',
            'dob', 'gender', 'gender_display', 'blood_type', 'blood_type_display',
            'phone_number', 'email', 'address', 'city',
            'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relation',
            'status', 'status_display',
            'organization', 'organization_name',
            'primary_hospital', 'primary_hospital_name',
            'allergies', 'medical_histories',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'medical_record_number', 'created_at', 'updated_at']


class PatientDemographicSerializer(serializers.ModelSerializer):
    """
    Administrative representation for Receptionists and Front-Desk staff.
    Hides detailed medical histories and blood type.
    Provides a boolean `has_allergies` flag for patient safety check-in.
    """
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    primary_hospital_name = serializers.CharField(source='primary_hospital.name', read_only=True)
    has_allergies = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = [
            'id', 'medical_record_number', 'first_name', 'last_name', 'full_name',
            'dob', 'gender', 'gender_display',
            'phone_number', 'email', 'address', 'city',
            'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relation',
            'status', 'status_display', 'has_allergies',
            'organization', 'organization_name',
            'primary_hospital', 'primary_hospital_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'medical_record_number', 'created_at', 'updated_at']

    def get_has_allergies(self, obj) -> bool:
        return obj.allergies.exists()


class PatientPharmacistSerializer(serializers.ModelSerializer):
    """
    Pharmacist representation.
    Focuses on medication safety: exposes full allergies and blood type,
    masks emergency contact and address.
    """
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    blood_type_display = serializers.CharField(source='get_blood_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    primary_hospital_name = serializers.CharField(source='primary_hospital.name', read_only=True)
    allergies = PatientAllergySerializer(many=True, read_only=True)

    class Meta:
        model = Patient
        fields = [
            'id', 'medical_record_number', 'first_name', 'last_name', 'full_name',
            'dob', 'gender', 'gender_display', 'blood_type', 'blood_type_display',
            'phone_number', 'city', 'status', 'status_display',
            'organization_name', 'primary_hospital_name',
            'allergies', 'created_at',
        ]
        read_only_fields = ['id', 'medical_record_number', 'created_at']


class PatientBillingSerializer(serializers.ModelSerializer):
    """
    Billing / Accounting representation.
    Per HIPAA / privacy standards, all clinical history and blood type are omitted.
    Only demographic and contact information necessary for billing is exposed.
    """
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    primary_hospital_name = serializers.CharField(source='primary_hospital.name', read_only=True)

    class Meta:
        model = Patient
        fields = [
            'id', 'medical_record_number', 'first_name', 'last_name', 'full_name',
            'phone_number', 'email', 'address', 'city',
            'status', 'status_display',
            'organization', 'organization_name',
            'primary_hospital', 'primary_hospital_name',
            'created_at',
        ]
        read_only_fields = ['id', 'medical_record_number', 'created_at']
