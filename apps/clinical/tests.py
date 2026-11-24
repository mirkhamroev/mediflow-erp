from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.organizations.models import Hospital, Organization, StaffProfile
from .models import Patient, PatientAllergy, PatientMedicalHistory


class PatientModelsTests(TestCase):
    def setUp(self):
        self.org1 = Organization.objects.create(
            name="Clinical Org 1",
            legal_name="Clinical Org 1 LLC",
            tax_id="TAX-CLN-1",
            address="10 Clinical Way",
            email="cln1@mediflow.com",
            phone_number="+998901112201",
        )
        self.org2 = Organization.objects.create(
            name="Clinical Org 2",
            legal_name="Clinical Org 2 LLC",
            tax_id="TAX-CLN-2",
            address="20 Clinical Way",
            email="cln2@mediflow.com",
            phone_number="+998901112202",
        )
        self.hosp1 = Hospital.objects.create(
            organization=self.org1,
            name="Clinical Hospital 1",
            code="CH-01",
            address="10 Clinical Way",
            city="Tashkent",
            phone_number="+998901112203",
            email="ch1@mediflow.com",
        )
        self.hosp2 = Hospital.objects.create(
            organization=self.org2,
            name="Clinical Hospital 2",
            code="CH-02",
            address="20 Clinical Way",
            city="Samarkand",
            phone_number="+998901112204",
            email="ch2@mediflow.com",
        )

    def test_patient_creation_and_auto_mrn_generation(self):
        patient = Patient.objects.create(
            first_name="John",
            last_name="Doe",
            dob=date(1990, 5, 15),
            gender=Patient.Gender.MALE,
            blood_type=Patient.BloodType.O_POS,
            phone_number="+998901234567",
            email="john.doe@example.com",
            organization=self.org1,
            primary_hospital=self.hosp1,
        )
        self.assertTrue(patient.medical_record_number.startswith("MRN-"))
        self.assertEqual(patient.full_name, "John Doe")
        self.assertEqual(str(patient), f"John Doe ({patient.medical_record_number})")
        self.assertEqual(patient.status, Patient.Status.ACTIVE)

    def test_future_dob_validation_fails(self):
        future_date = date.today() + timedelta(days=1)
        patient = Patient(
            first_name="Future",
            last_name="Baby",
            dob=future_date,
            gender=Patient.Gender.FEMALE,
            phone_number="+998901234568",
        )
        with self.assertRaises(ValidationError):
            patient.full_clean()

    def test_primary_hospital_mismatched_organization_clean_fails(self):
        patient = Patient(
            first_name="Jane",
            last_name="Smith",
            dob=date(1985, 2, 20),
            phone_number="+998901234569",
            organization=self.org1,
            primary_hospital=self.hosp2,  # belongs to org2!
        )
        with self.assertRaises(ValidationError):
            patient.clean()

    def test_patient_allergy_and_medical_history_relations(self):
        patient = Patient.objects.create(
            first_name="Alice",
            last_name="Wonderland",
            dob=date(1995, 8, 10),
            phone_number="+998901234570",
            organization=self.org1,
            primary_hospital=self.hosp1,
        )

        allergy = PatientAllergy.objects.create(
            patient=patient,
            allergen="Penicillin",
            severity=PatientAllergy.Severity.SEVERE,
            reaction="Anaphylactic shock",
        )
        self.assertEqual(str(allergy), "Alice Wonderland - Penicillin (Severe)")
        self.assertEqual(patient.allergies.count(), 1)

        history = PatientMedicalHistory.objects.create(
            patient=patient,
            condition_name="Type 1 Diabetes",
            is_chronic=True,
            diagnosis_date=date(2010, 3, 1),
        )
        self.assertEqual(str(history), "Alice Wonderland - Type 1 Diabetes")
        self.assertEqual(patient.medical_histories.count(), 1)


class PatientAPIPrivacyAndScopingTests(APITestCase):
    def setUp(self):
        self.password = "StrongPassword123!"

        # Organization 1 & Hospital 1
        self.org1 = Organization.objects.create(
            name="Org One", legal_name="Org One LLC", tax_id="TAX-1",
            address="1 St", email="org1@test.com", phone_number="+998900000001",
        )
        self.hosp1 = Hospital.objects.create(
            organization=self.org1, name="Hosp One", code="H-01",
            address="1 St", city="Tashkent", phone_number="+998900000002", email="h1@test.com",
        )

        # Organization 2 (Tenant isolation test)
        self.org2 = Organization.objects.create(
            name="Org Two", legal_name="Org Two LLC", tax_id="TAX-2",
            address="2 St", email="org2@test.com", phone_number="+998900000003",
        )
        self.hosp2 = Hospital.objects.create(
            organization=self.org2, name="Hosp Two", code="H-02",
            address="2 St", city="Samarkand", phone_number="+998900000004", email="h2@test.com",
        )

        # Staff Users in Org 1
        self.doctor = User.objects.create_user(
            email="doc@org1.com", phone_number="+998900000010", full_name="Dr. Gregory",
            password=self.password, role=User.Role.DOCTOR, is_active=True,
        )
        StaffProfile.objects.create(
            user=self.doctor, organization=self.org1, hospital=self.hosp1,
            employee_id="DOC-1", hire_date=date(2024, 1, 1),
        )

        self.receptionist = User.objects.create_user(
            email="reception@org1.com", phone_number="+998900000011", full_name="Pam Beesly",
            password=self.password, role=User.Role.RECEPTIONIST, is_active=True,
        )
        StaffProfile.objects.create(
            user=self.receptionist, organization=self.org1, hospital=self.hosp1,
            employee_id="REC-1", hire_date=date(2024, 1, 1),
        )

        self.pharmacist = User.objects.create_user(
            email="pharm@org1.com", phone_number="+998900000012", full_name="Walter White",
            password=self.password, role=User.Role.PHARMACIST, is_active=True,
        )
        StaffProfile.objects.create(
            user=self.pharmacist, organization=self.org1, hospital=self.hosp1,
            employee_id="PHARM-1", hire_date=date(2024, 1, 1),
        )

        self.accountant = User.objects.create_user(
            email="accountant@org1.com", phone_number="+998900000013", full_name="Oscar Martinez",
            password=self.password, role=User.Role.ACCOUNTANT, is_active=True,
        )
        StaffProfile.objects.create(
            user=self.accountant, organization=self.org1, hospital=self.hosp1,
            employee_id="ACC-1", hire_date=date(2024, 1, 1),
        )

        # Patients: Patient 1 in Org 1, Patient 2 in Org 2
        self.patient1 = Patient.objects.create(
            first_name="Bruce", last_name="Wayne", dob=date(1980, 2, 19),
            gender=Patient.Gender.MALE, blood_type=Patient.BloodType.O_NEG,
            phone_number="+998901234001", email="bruce@wayne.com", address="Wayne Manor 100",
            city="Gotham", emergency_contact_name="Alfred", emergency_contact_phone="+998901234999",
            emergency_contact_relation="Butler", organization=self.org1, primary_hospital=self.hosp1,
        )
        PatientAllergy.objects.create(
            patient=self.patient1, allergen="Latex", severity=PatientAllergy.Severity.MODERATE,
            reaction="Skin rash",
        )
        PatientMedicalHistory.objects.create(
            patient=self.patient1, condition_name="Multiple Contusions", is_chronic=False,
            diagnosis_date=date(2024, 5, 10),
        )

        self.patient2 = Patient.objects.create(
            first_name="Clark", last_name="Kent", dob=date(1982, 6, 18),
            gender=Patient.Gender.MALE, blood_type=Patient.BloodType.AB_POS,
            phone_number="+998901234002", email="clark@dailyplanet.com", address="Metropolis",
            city="Metropolis", organization=self.org2, primary_hospital=self.hosp2,
        )

    def test_multi_tenant_row_scoping_hides_other_organizations_patients(self):
        self.client.force_authenticate(user=self.doctor)
        res = self.client.get("/api/clinical/patients/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["first_name"], "Bruce")

        # Directly requesting Patient 2 (Org 2) returns 404 Not Found
        res_other = self.client.get(f"/api/clinical/patients/{self.patient2.pk}/")
        self.assertEqual(res_other.status_code, status.HTTP_404_NOT_FOUND)

    def test_doctor_sees_full_clinical_data(self):
        self.client.force_authenticate(user=self.doctor)
        res = self.client.get(f"/api/clinical/patients/{self.patient1.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Full clinical data present
        self.assertIn("blood_type", res.data)
        self.assertEqual(res.data["blood_type"], "O-")
        self.assertEqual(len(res.data["allergies"]), 1)
        self.assertEqual(res.data["allergies"][0]["allergen"], "Latex")
        self.assertEqual(len(res.data["medical_histories"]), 1)
        self.assertEqual(res.data["medical_histories"][0]["condition_name"], "Multiple Contusions")
        self.assertEqual(res.data["emergency_contact_name"], "Alfred")

    def test_receptionist_sees_demographics_with_allergy_flag_but_no_medical_histories(self):
        self.client.force_authenticate(user=self.receptionist)
        res = self.client.get(f"/api/clinical/patients/{self.patient1.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Demographics present
        self.assertEqual(res.data["first_name"], "Bruce")
        self.assertEqual(res.data["emergency_contact_name"], "Alfred")
        # Safety flag present
        self.assertEqual(res.data["has_allergies"], True)

        # Confidential medical data omitted
        self.assertNotIn("blood_type", res.data)
        self.assertNotIn("allergies", res.data)
        self.assertNotIn("medical_histories", res.data)

    def test_pharmacist_sees_allergies_and_blood_type_but_masks_emergency_contacts(self):
        self.client.force_authenticate(user=self.pharmacist)
        res = self.client.get(f"/api/clinical/patients/{self.patient1.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Medication safety fields present
        self.assertEqual(res.data["blood_type"], "O-")
        self.assertEqual(len(res.data["allergies"]), 1)
        self.assertEqual(res.data["allergies"][0]["allergen"], "Latex")

        # Irrelevant personal fields omitted
        self.assertNotIn("emergency_contact_name", res.data)
        self.assertNotIn("address", res.data)
        self.assertNotIn("medical_histories", res.data)

    def test_accountant_sees_billing_contact_only_with_all_medical_data_masked(self):
        self.client.force_authenticate(user=self.accountant)
        res = self.client.get(f"/api/clinical/patients/{self.patient1.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Billing identity fields present
        self.assertEqual(res.data["first_name"], "Bruce")
        self.assertEqual(res.data["phone_number"], "+998901234001")
        self.assertEqual(res.data["city"], "Gotham")

        # All medical data masked
        self.assertNotIn("blood_type", res.data)
        self.assertNotIn("allergies", res.data)
        self.assertNotIn("medical_histories", res.data)
        self.assertNotIn("emergency_contact_name", res.data)

    def test_duplicate_patient_detection_blocks_registration(self):
        self.client.force_authenticate(user=self.receptionist)
        duplicate_payload = {
            "first_name": "Bruce",
            "last_name": "Wayne",
            "dob": "1980-02-19",
            "gender": "male",
            "phone_number": "+998901234001",
            "organization": str(self.org1.pk),
            "primary_hospital": str(self.hosp1.pk),
        }
        res = self.client.post("/api/clinical/patients/", duplicate_payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Duplicate patient detected", str(res.data))

    def test_clinical_subresource_permissions(self):
        # Accountant is forbidden from viewing patient allergies endpoint
        self.client.force_authenticate(user=self.accountant)
        res_allergy_acc = self.client.get("/api/clinical/allergies/")
        self.assertEqual(res_allergy_acc.status_code, status.HTTP_403_FORBIDDEN)

        # Receptionist is forbidden from viewing medical histories endpoint
        self.client.force_authenticate(user=self.receptionist)
        res_history_rec = self.client.get("/api/clinical/medical-histories/")
        self.assertEqual(res_history_rec.status_code, status.HTTP_403_FORBIDDEN)

        # Doctor can create an allergy record
        self.client.force_authenticate(user=self.doctor)
        allergy_payload = {
            "patient": str(self.patient1.pk),
            "allergen": "Aspirin",
            "severity": "mild",
            "reaction": "Mild hives",
        }
        res_create_allergy = self.client.post("/api/clinical/allergies/", allergy_payload, format="json")
        self.assertEqual(res_create_allergy.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_create_allergy.data["allergen"], "Aspirin")
