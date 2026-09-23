# ===== CHANGE #32 (step 6): tests for the JWT login, /me/ profile endpoint and the
# two-step email change (request -> confirm). =====
"""Profile update + email-change flow.

CELERY_TASK_ALWAYS_EAGER runs the email task inline, so the code lands in
django.core.mail.outbox (see test_verification.py for the same setup).
"""
import base64
import os
import re
import tempfile
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, EmailVerificationOTP

PASSWORD = "supersecret1"
OLD_EMAIL = "doctor@example.com"
NEW_EMAIL = "doctor.new@example.com"


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class ProfileAndEmailChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email=OLD_EMAIL,
            phone_number="+998901234567",
            password=PASSWORD,
            full_name="Dr. Test",
            is_active=True,
        )
        self.client = APIClient()
        token = self.client.post(
            reverse("token-obtain"), {"email": OLD_EMAIL, "password": PASSWORD}, format="json"
        ).json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def request_change(self, new_email=NEW_EMAIL, password=PASSWORD):
        # on_commit callbacks never fire inside TestCase's transaction; run them.
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("email-change"),
                {"new_email": new_email, "password": password},
                format="json",
            )

    def confirm(self, code):
        return self.client.post(reverse("email-change-confirm"), {"code": code}, format="json")

    @staticmethod
    def code_from_outbox():
        return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)

    # ----- /me/ -----

    def test_me_requires_authentication(self):
        self.assertEqual(APIClient().get(reverse("me")).status_code, 401)

    def test_patch_updates_profile_but_not_email_or_role(self):
        response = self.client.patch(
            reverse("me"),
            {"full_name": "Dr. Renamed", "email": "hijack@example.com", "role": "admin"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Dr. Renamed")
        self.assertEqual(self.user.email, OLD_EMAIL)
        self.assertEqual(self.user.role, User.Role.USER)
        self.assertEqual(len(mail.outbox), 0)  # a name change sends no email

    def test_patch_rejects_taken_phone_number(self):
        User.objects.create_user(
            email="other@example.com", phone_number="+998909999999",
            password=PASSWORD, full_name="Other",
        )
        response = self.client.patch(reverse("me"), {"phone_number": "+998909999999"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_put_is_not_allowed(self):
        self.assertEqual(self.client.put(reverse("me"), {}, format="json").status_code, 405)

    # 1x1 transparent PNG
    PNG_BYTES = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )

    def upload_image(self, name="avatar.png"):
        return self.client.patch(
            reverse("me"),
            {"image": SimpleUploadedFile(name, self.PNG_BYTES, content_type="image/png")},
            format="multipart",
        )

    def test_patch_replacing_image_deletes_old_file(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            self.assertEqual(self.upload_image("first.png").status_code, 200)
            self.user.refresh_from_db()
            old_path = self.user.image.path
            self.assertTrue(os.path.exists(old_path))

            self.assertEqual(self.upload_image("second.png").status_code, 200)
            self.user.refresh_from_db()
            self.assertIn("second", self.user.image.name)
            self.assertFalse(os.path.exists(old_path))  # old file is gone

    def test_patch_clearing_image_deletes_old_file(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            self.assertEqual(self.upload_image().status_code, 200)
            self.user.refresh_from_db()
            old_path = self.user.image.path

            response = self.client.patch(reverse("me"), {"image": ""}, format="multipart")
            self.assertEqual(response.status_code, 200)
            self.user.refresh_from_db()
            self.assertFalse(self.user.image)
            self.assertFalse(os.path.exists(old_path))

    def test_patch_rejects_oversized_image(self):
        big = SimpleUploadedFile(
            "big.png", b"\x00" * (5 * 1024 * 1024 + 1), content_type="image/png"
        )
        response = self.client.patch(reverse("me"), {"image": big}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_patch_is_rejected(self):
        self.assertEqual(APIClient().patch(reverse("me"), {}, format="json").status_code, 401)

    def test_delete_deactivates_instead_of_deleting(self):
        self.assertEqual(self.client.delete(reverse("me")).status_code, 204)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        # the old token is now useless
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)

    # ----- email change -----

    def test_request_sends_code_to_new_address_without_changing_email(self):
        response = self.request_change()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mail.outbox[-1].to, [NEW_EMAIL])
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, OLD_EMAIL)
        otp = self.user.otps.get()
        self.assertEqual(otp.purpose, EmailVerificationOTP.PURPOSE.EMAIL_CHANGE)
        self.assertEqual(otp.new_email, NEW_EMAIL)

    def test_request_with_wrong_password_is_rejected(self):
        self.assertEqual(self.request_change(password="wrong-password").status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_with_taken_email_is_rejected(self):
        self.assertEqual(self.request_change(new_email=OLD_EMAIL).status_code, 400)

    def test_confirm_with_correct_code_changes_email(self):
        self.request_change()

        response = self.confirm(self.code_from_outbox())

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, NEW_EMAIL)
        self.assertTrue(self.user.otps.get().is_used)

    def test_confirm_with_wrong_code_spends_an_attempt(self):
        self.request_change()
        wrong = "000000" if self.code_from_outbox() != "000000" else "111111"

        self.assertEqual(self.confirm(wrong).status_code, 400)
        self.assertEqual(self.user.otps.get().attempts, 4)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, OLD_EMAIL)

    def test_confirm_with_expired_code_is_rejected(self):
        self.request_change()
        code = self.code_from_outbox()
        EmailVerificationOTP.objects.update(expires_at=timezone.now() - timedelta(minutes=1))

        self.assertEqual(self.confirm(code).status_code, 400)

    def test_new_request_retires_previous_code(self):
        self.request_change()
        first_code = self.code_from_outbox()
        self.request_change(new_email="third@example.com")

        response = self.confirm(first_code)

        # only the newest code is live; the first one was burned by the second request
        if first_code != self.code_from_outbox():
            self.assertEqual(response.status_code, 400)

    def test_confirm_fails_if_address_was_taken_meanwhile(self):
        self.request_change()
        User.objects.create_user(
            email=NEW_EMAIL, phone_number="+998908888888",
            password=PASSWORD, full_name="Faster",
        )

        self.assertEqual(self.confirm(self.code_from_outbox()).status_code, 400)

    def test_registration_verify_endpoint_does_not_accept_email_change_code(self):
        self.request_change()
        response = self.client.post(
            reverse("verify-email"),
            {"email": OLD_EMAIL, "code": self.code_from_outbox()},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
