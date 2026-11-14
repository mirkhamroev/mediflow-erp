from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
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
    Bed,
    Department,
    DoctorProfile,
    Hospital,
    NurseProfile,
    OperatingRoom,
    Organization,
    Room,
    StaffProfile,
    Ward,
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

    def test_ward_room_bed_and_operating_room_models(self):
        ward = Ward.objects.create(
            hospital=self.hosp1,
            department=self.dept1,
            name="Intensive Care Unit A",
            code="WARD-ICU-A",
            ward_type=Ward.WardType.ICU,
            floor=3,
        )
        self.assertEqual(str(ward), "Intensive Care Unit A - Fl. 3 (North General)")

        room = Room.objects.create(
            ward=ward,
            room_number="301-A",
            room_type=Room.RoomType.ICU,
            daily_rate=Decimal("250.00"),
        )
        self.assertEqual(str(room), "Room 301-A (Intensive Care Unit A)")

        bed = Bed.objects.create(
            room=room,
            bed_number="BED-01",
            status=Bed.BedStatus.AVAILABLE,
        )
        self.assertEqual(str(bed), "Bed BED-01 - Room 301-A")

        or_room = OperatingRoom.objects.create(
            hospital=self.hosp1,
            department=self.dept1,
            name="Cardiothoracic OR 1",
            code="OR-CARD-01",
            specialty="Cardiothoracic Surgery",
            status=OperatingRoom.ORStatus.AVAILABLE,
        )
        self.assertEqual(str(or_room), "Cardiothoracic OR 1 (North General)")

    def test_facility_models_clean_validation_and_unique_constraints(self):
        dept2 = Department.objects.create(
            hospital=self.hosp2,
            name="Pediatrics South",
            code="PEDS",
        )
        # Ward with department belonging to another hospital must fail clean()
        mismatched_ward = Ward(
            hospital=self.hosp1,
            department=dept2,  # belongs to hosp2!
            name="Invalid Ward",
            code="WARD-INV",
            floor=1,
        )
        with self.assertRaises(ValidationError):
            mismatched_ward.clean()

        # OperatingRoom with mismatched department must fail clean()
        mismatched_or = OperatingRoom(
            hospital=self.hosp1,
            department=dept2,  # belongs to hosp2!
            name="Invalid OR",
            code="OR-INV",
        )
        with self.assertRaises(ValidationError):
            mismatched_or.clean()

        # Unique constraints: duplicate ward code per hospital
        Ward.objects.create(
            hospital=self.hosp1,
            name="Ward 1",
            code="W-01",
            floor=1,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Ward.objects.create(
                    hospital=self.hosp1,
                    name="Duplicate Code Ward",
                    code="W-01",
                    floor=2,
                )

        # Same code in different hospital is allowed
        ward_hosp2 = Ward.objects.create(
            hospital=self.hosp2,
            name="Ward 1 South",
            code="W-01",
            floor=1,
        )
        self.assertIsNotNone(ward_hosp2.pk)


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


class FacilityEndpointsAPITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Apex Health",
            legal_name="Apex Health LLC",
            tax_id="TAX-APX1",
            address="100 Medical Way",
            email="apex@health.com",
            phone_number="+998901110001",
        )
        self.hospital = Hospital.objects.create(
            organization=self.org,
            name="Apex General",
            code="AG-01",
            address="100 Medical Way",
            city="Tashkent",
            phone_number="+998901110002",
            email="ag@apex.com",
        )
        self.dept = Department.objects.create(
            hospital=self.hospital,
            name="Cardiology",
            code="CARD",
        )
        self.admin_user = User.objects.create_user(
            email="facility.admin@apex.com",
            phone_number="+998901110003",
            full_name="Facility Administrator",
            password="StrongPassword123!",
            role=User.Role.ADMIN,
            is_active=True,
        )
        self.doctor_user = User.objects.create_user(
            email="facility.doc@apex.com",
            phone_number="+998901110004",
            full_name="Dr. Facility",
            password="StrongPassword123!",
            role=User.Role.DOCTOR,
            is_active=True,
        )

    def test_facility_crud_by_admin_and_forbidden_for_regular_staff(self):
        # 1. Unauthenticated gets 401
        res = self.client.get("/api/organizations/wards/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Doctor gets 403 on write
        self.client.force_authenticate(user=self.doctor_user)
        ward_payload = {
            "hospital": str(self.hospital.pk),
            "department": str(self.dept.pk),
            "name": "Cardiology Ward",
            "code": "WARD-CARD-1",
            "ward_type": Ward.WardType.CARDIAC if hasattr(Ward.WardType, 'CARDIAC') else Ward.WardType.ICU,
            "floor": 2,
        }
        res_forbidden = self.client.post("/api/organizations/wards/", ward_payload, format="json")
        self.assertEqual(res_forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Admin successfully creates Ward
        self.client.force_authenticate(user=self.admin_user)
        res_ward = self.client.post("/api/organizations/wards/", ward_payload, format="json")
        self.assertEqual(res_ward.status_code, status.HTTP_201_CREATED)
        ward_id = res_ward.data["id"]

        # 4. Admin creates Room inside Ward
        room_payload = {
            "ward": ward_id,
            "room_number": "201-C",
            "room_type": Room.RoomType.ICU,
            "daily_rate": "150.00",
        }
        res_room = self.client.post("/api/organizations/rooms/", room_payload, format="json")
        self.assertEqual(res_room.status_code, status.HTTP_201_CREATED)
        room_id = res_room.data["id"]

        # 5. Admin creates Bed inside Room
        bed_payload = {
            "room": room_id,
            "bed_number": "B-01",
            "status": Bed.BedStatus.AVAILABLE,
        }
        res_bed = self.client.post("/api/organizations/beds/", bed_payload, format="json")
        self.assertEqual(res_bed.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_bed.data["bed_number"], "B-01")

        # 6. Admin creates Operating Room
        or_payload = {
            "hospital": str(self.hospital.pk),
            "department": str(self.dept.pk),
            "name": "Hybrid Cardiovascular Suite",
            "code": "OR-HCV-01",
            "specialty": "Cardiology",
            "status": OperatingRoom.ORStatus.AVAILABLE,
        }
        res_or = self.client.post("/api/organizations/operating-rooms/", or_payload, format="json")
        self.assertEqual(res_or.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_or.data["name"], "Hybrid Cardiovascular Suite")

        # 7. Authenticated user can read facilities
        self.client.force_authenticate(user=self.doctor_user)
        list_wards = self.client.get("/api/organizations/wards/")
        self.assertEqual(list_wards.status_code, status.HTTP_200_OK)
        self.assertEqual(list_wards.data["count"], 1)
        self.assertEqual(list_wards.data["results"][0]["hospital_name"], "Apex General")

        # 8. Retrieve single ward triggers audit view
        retrieve_ward = self.client.get(f"/api/organizations/wards/{ward_id}/")
        self.assertEqual(retrieve_ward.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_ward.data["name"], "Cardiology Ward")


