from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.organizations.models import Department, Hospital, Organization


class AuditLogImmutabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="doctor@mediflow.com",
            phone_number="+998901112233",
            full_name="Dr. House",
            password="StrongPassword123!",
            role=User.Role.DOCTOR,
            is_active=True,
        )

    def test_audit_log_cannot_be_updated_or_deleted(self):
        entry = AuditLog.objects.filter(
            model_name="accounts.User", object_id=str(self.user.pk), action="create"
        ).first()
        self.assertIsNotNone(entry)

        entry.action = "delete"
        with self.assertRaises(PermissionDenied):
            entry.save()

        with self.assertRaises(PermissionDenied):
            entry.delete()

        with self.assertRaises(PermissionDenied):
            AuditLog.objects.filter(pk=entry.pk).update(action="delete")

        with self.assertRaises(PermissionDenied):
            AuditLog.objects.filter(pk=entry.pk).delete()


class AuditSignalWiringTests(TestCase):
    def test_user_create_update_delete_and_password_masking(self):
        user = User.objects.create_user(
            email="nurse@mediflow.com",
            phone_number="+998901112244",
            full_name="Nurse Joy",
            password="StrongPassword123!",
            role=User.Role.NURSE,
            is_active=True,
        )
        create_log = AuditLog.objects.filter(
            model_name="accounts.User", object_id=str(user.pk), action="create"
        ).first()
        self.assertIsNotNone(create_log)
        self.assertEqual(create_log.new_values["email"], "nurse@mediflow.com")
        self.assertEqual(create_log.new_values["password"], "***")

        # Update full_name -> only full_name is recorded in old/new values
        user.full_name = "Head Nurse Joy"
        user.save()
        update_log = AuditLog.objects.filter(
            model_name="accounts.User", object_id=str(user.pk), action="update"
        ).first()
        self.assertIsNotNone(update_log)
        self.assertEqual(update_log.old_values, {"full_name": "Nurse Joy"})
        self.assertEqual(update_log.new_values, {"full_name": "Head Nurse Joy"})

        # No-op save produces no extra update entry
        user.save()
        self.assertEqual(
            AuditLog.objects.filter(
                model_name="accounts.User", object_id=str(user.pk), action="update"
            ).count(),
            1,
        )

    def test_organization_hospital_department_audited_including_cascade_delete(self):
        org = Organization.objects.create(
            name="MediFlow Group",
            legal_name="MediFlow Group LLC",
            tax_id="TAX-001",
            address="123 Health Ave",
            email="info@mediflow.com",
            phone_number="+998901234567",
        )
        hospital = Hospital.objects.create(
            organization=org,
            name="Central Hospital",
            code="CH-01",
            address="123 Health Ave",
            city="Tashkent",
            phone_number="+998901234568",
            email="ch@mediflow.com",
        )
        dept = Department.objects.create(
            hospital=hospital,
            name="Cardiology",
            code="CARD",
        )

        self.assertTrue(
            AuditLog.objects.filter(
                model_name="organizations.Organization", object_id=str(org.pk), action="create"
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                model_name="organizations.Hospital", object_id=str(hospital.pk), action="create"
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                model_name="organizations.Department", object_id=str(dept.pk), action="create"
            ).exists()
        )

        # Cascading delete of Organization logs DELETE for Organization, Hospital, and Department
        dept_id = str(dept.pk)
        hospital_id = str(hospital.pk)
        org_id = str(org.pk)
        org.delete()

        self.assertTrue(
            AuditLog.objects.filter(
                model_name="organizations.Department", object_id=dept_id, action="delete"
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                model_name="organizations.Hospital", object_id=hospital_id, action="delete"
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                model_name="organizations.Organization", object_id=org_id, action="delete"
            ).exists()
        )


class AuditAPITests(APITestCase):
    def setUp(self):
        self.password = "StrongPassword123!"
        self.admin_user = User.objects.create_user(
            email="admin@mediflow.com",
            phone_number="+998909998877",
            full_name="Hospital Admin",
            password=self.password,
            role=User.Role.ADMIN,
            is_active=True,
            is_staff=True,
        )
        self.doctor_user = User.objects.create_user(
            email="doc@mediflow.com",
            phone_number="+998909998866",
            full_name="Dr. Smith",
            password=self.password,
            role=User.Role.DOCTOR,
            is_active=True,
        )
        self.org = Organization.objects.create(
            name="Sunrise Health",
            legal_name="Sunrise Health LLC",
            tax_id="TAX-999",
            address="456 Wellness Blvd",
            email="contact@sunrise.com",
            phone_number="+998905554433",
        )

    def test_jwt_login_and_logout_write_audit_logs(self):
        login_res = self.client.post(
            reverse("token-obtain"),
            {"email": self.doctor_user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertTrue(
            AuditLog.objects.filter(
                action="login", user=self.doctor_user, model_name="accounts.User"
            ).exists()
        )

        refresh_token = login_res.data["refresh"]
        logout_res = self.client.post(
            reverse("token-blacklist"),
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)
        self.assertTrue(
            AuditLog.objects.filter(
                action="logout", user=self.doctor_user, model_name="accounts.User"
            ).exists()
        )

    def test_retrieve_organization_logs_view_action_with_actor(self):
        self.client.force_authenticate(user=self.doctor_user)
        res = self.client.get(f"/api/organizations/organizations/{self.org.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        view_log = AuditLog.objects.filter(
            action="view",
            model_name="organizations.Organization",
            object_id=str(self.org.pk),
            user=self.doctor_user,
        ).first()
        self.assertIsNotNone(view_log)
        self.assertEqual(view_log.username, self.doctor_user.email)
        self.assertEqual(view_log.user_role, User.Role.DOCTOR)

    def test_audit_log_api_permissions_and_filtering(self):
        # Non-admin (doctor) cannot access /api/audit/logs/
        self.client.force_authenticate(user=self.doctor_user)
        forbidden_res = self.client.get("/api/audit/logs/")
        self.assertEqual(forbidden_res.status_code, status.HTTP_403_FORBIDDEN)

        # Admin can list and filter audit logs
        self.client.force_authenticate(user=self.admin_user)
        ok_res = self.client.get(
            "/api/audit/logs/",
            {"model_name": "organizations.Organization", "object_id": str(self.org.pk)},
        )
        self.assertEqual(ok_res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(ok_res.data["count"], 1)

        # Write methods are not allowed on ReadOnlyModelViewSet
        post_res = self.client.post("/api/audit/logs/", {"action": "create"})
        self.assertEqual(post_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

