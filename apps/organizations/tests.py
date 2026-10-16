from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory

from apps.accounts.models import Permission, Role, User, UserRole
from apps.commons.permissions import (
    HasRBACPermission,
    IsClinicalStaff,
    IsDoctor,
    IsHospitalAdmin,
    IsInsuranceManager,
    IsNurse,
    IsOwner,
    IsReceptionist,
    IsSameHospital,
    IsSameOrganization,
    RoleBasedPermission,
)
from apps.organizations.models import (
    Department,
    DoctorProfile,
    Hospital,
    NurseProfile,
    Organization,
    StaffProfile,
)


class OrganizationStaffModelsTests(TestCase):
    def setUp(self):
        self.org1 = Organization.objects.create(
            name="MediFlow North",
            legal_name="MediFlow North LLC",
            tax_id="TAX-N1",
            address="1 North St",
            email="north@mediflow.com",
            phone_number="+998901000001",
        )
        self.org2 = Organization.objects.create(
            name="MediFlow South",
            legal_name="MediFlow South LLC",
            tax_id="TAX-S1",
            address="1 South St",
            email="south@mediflow.com",
            phone_number="+998901000002",
        )
        self.hosp1 = Hospital.objects.create(
            organization=self.org1,
            name="North General",
            code="NG-01",
            address="1 North St",
            city="Tashkent",
            phone_number="+998901000003",
            email="ng@mediflow.com",
        )
        self.hosp2 = Hospital.objects.create(
            organization=self.org2,
            name="South General",
            code="SG-01",
            address="1 South St",
            city="Samarkand",
            phone_number="+998901000004",
            email="sg@mediflow.com",
        )
        self.dept1 = Department.objects.create(
            hospital=self.hosp1,
            name="Surgery",
            code="SURG",
        )
        self.doc_user = User.objects.create_user(
            email="surgeon@mediflow.com",
            phone_number="+998901000005",
            full_name="Gregory House",
            password="StrongPassword123!",
            role=User.Role.DOCTOR,
            is_active=True,
        )
        self.nurse_user = User.objects.create_user(
            email="nurse@mediflow.com",
            phone_number="+998901000006",
            full_name="Carla Espinosa",
            password="StrongPassword123!",
            role=User.Role.NURSE,
            is_active=True,
        )

    def test_staff_doctor_and_nurse_profiles_and_employee_id_scoped_per_organization(self):
        doc_staff = StaffProfile.objects.create(
            user=self.doc_user,
            organization=self.org1,
            hospital=self.hosp1,
            department=self.dept1,
            employee_id="EMP-001",
            hire_date=date(2025, 1, 15),
        )
        # Same employee_id in a different organization is allowed
        nurse_staff = StaffProfile.objects.create(
            user=self.nurse_user,
            organization=self.org2,
            hospital=self.hosp2,
            employee_id="EMP-001",
            hire_date=date(2025, 2, 1),
        )
        self.assertEqual(str(doc_staff), "Gregory House - EMP-001")
        self.assertEqual(str(nurse_staff), "Carla Espinosa - EMP-001")

        doc_profile = DoctorProfile.objects.create(
            staff_profile=doc_staff,
            specialization="Diagnostic Medicine",
            years_of_experience=15,
            consultation_fee=Decimal("150.00"),
            license_number="DOC-LIC-001",
            license_expiry_date=date(2030, 12, 31),
        )
        nurse_profile = NurseProfile.objects.create(
            staff_profile=nurse_staff,
            license_number="NUR-LIC-001",
            license_expiry_date=date(2030, 12, 31),
            nurse_level="RN",
            shift=NurseProfile.NursingShift.DAY,
            nursing_specialty="ICU",
        )
        self.assertEqual(str(doc_profile), "Dr. Gregory House - Diagnostic Medicine")
        self.assertEqual(str(nurse_profile), "Nurse Carla Espinosa")

    def test_staff_profile_clean_rejects_mismatched_hospital_or_department(self):
        mismatched = StaffProfile(
            user=self.doc_user,
            organization=self.org1,
            hospital=self.hosp2,  # belongs to org2!
            employee_id="EMP-999",
            hire_date=date(2025, 1, 1),
        )
        with self.assertRaises(ValidationError):
            mismatched.clean()


class RBACAndPermissionsTests(APITestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.org = Organization.objects.create(
            name="MediFlow Central",
            legal_name="MediFlow Central LLC",
            tax_id="TAX-C1",
            address="10 Main St",
            email="central@mediflow.com",
            phone_number="+998902000001",
        )
        self.hospital = Hospital.objects.create(
            organization=self.org,
            name="Central Clinic",
            code="CC-01",
            address="10 Main St",
            city="Tashkent",
            phone_number="+998902000002",
            email="cc@mediflow.com",
        )
        self.admin_user = User.objects.create_user(
            email="hospital.admin@mediflow.com",
            phone_number="+998902000003",
            full_name="Lisa Cuddy",
            password="StrongPassword123!",
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=False,  # Hospital admin by role, even without Django admin `is_staff`
        )
        self.doctor_user = User.objects.create_user(
            email="wilson@mediflow.com",
            phone_number="+998902000004",
            full_name="James Wilson",
            password="StrongPassword123!",
            role=User.Role.DOCTOR,
            is_active=True,
        )

    def test_rbac_models_permission_role_and_user_role(self):
        perm_read = Permission.objects.create(
            code="clinical.read",
            name="Read Clinical Records",
            module="clinical",
        )
        perm_prescribe = Permission.objects.create(
            code="clinical.create_prescription",
            name="Create Prescription",
            module="clinical",
        )
        perm_dispense = Permission.objects.create(
            code="inventory.dispense",
            name="Dispense Medication",
            module="inventory",
        )

        doctor_role = Role.objects.create(code="doctor", name="Doctor")
        doctor_role.permissions.add(perm_read, perm_prescribe)

        oncall_role = Role.objects.create(code="oncall_lead", name="On-Call Lead")
        oncall_role.permissions.add(perm_dispense)

        # Doctor gets permissions from Role matching primary `user.role == 'doctor'`
        self.assertTrue(self.doctor_user.has_rbac_perm("clinical.read"))
        self.assertTrue(self.doctor_user.has_rbac_perm("clinical.create_prescription"))
        self.assertFalse(self.doctor_user.has_rbac_perm("inventory.dispense"))

        # Assigning an extra UserRole grants its permissions too
        UserRole.objects.create(user=self.doctor_user, role=oncall_role, assigned_by=self.admin_user)
        self.assertTrue(self.doctor_user.has_role("oncall_lead"))
        self.assertTrue(self.doctor_user.has_rbac_perm("inventory.dispense"))

    def test_hospital_admin_can_create_staff_profile_via_api_and_doctor_cannot(self):
        payload = {
            "user": str(self.doctor_user.pk),
            "organization": str(self.org.pk),
            "hospital": str(self.hospital.pk),
            "employee_id": "DOC-100",
            "hire_date": "2026-01-10",
        }

        # Doctor is forbidden from creating staff profiles
        self.client.force_authenticate(user=self.doctor_user)
        forbidden = self.client.post("/api/organizations/staff-profiles/", payload, format="json")
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # Hospital admin (role='admin', even with is_staff=False) is allowed
        self.client.force_authenticate(user=self.admin_user)
        created = self.client.post("/api/organizations/staff-profiles/", payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["employee_id"], "DOC-100")

    def test_is_same_organization_and_is_owner_object_permissions(self):
        staff = StaffProfile.objects.create(
            user=self.doctor_user,
            organization=self.org,
            hospital=self.hospital,
            employee_id="DOC-200",
            hire_date=date(2026, 1, 1),
        )
        other_org = Organization.objects.create(
            name="Other Org",
            legal_name="Other Org LLC",
            tax_id="TAX-O1",
            address="99 Other St",
            email="other@org.com",
            phone_number="+998902000099",
        )

        req = self.factory.get("/")
        req.user = self.doctor_user

        same_org_perm = IsSameOrganization()
        self.assertTrue(same_org_perm.has_object_permission(req, None, self.hospital))
        self.assertFalse(same_org_perm.has_object_permission(req, None, other_org))

        owner_perm = IsOwner()
        self.assertTrue(owner_perm.has_permission(req, None))
        self.assertTrue(owner_perm.has_object_permission(req, None, staff))

