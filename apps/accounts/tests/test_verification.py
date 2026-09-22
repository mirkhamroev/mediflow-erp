"""End-to-end tests for the registration + email-verification flow.

CELERY_TASK_ALWAYS_EAGER runs send_async_email inline instead of pushing it to
Redis, so no broker is needed and the mail lands in django.core.mail.outbox.
"""
import re

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User, EmailVerificationOTP

REGISTER_PAYLOAD = {
    "email": "patient@example.com",
    "phone_number": "+998901234567",
    "password": "supersecret1",
    "full_name": "Test Patient",
}


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class EmailVerificationFlowTests(TestCase):
    def register(self, **overrides):
        payload = {**REGISTER_PAYLOAD, **overrides}
        # TestCase wraps each test in a transaction that is rolled back, so
        # transaction.on_commit() callbacks never run on their own -- and the
        # email is enqueued from on_commit. captureOnCommitCallbacks executes
        # them so the mail actually reaches mail.outbox.
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("register"), payload, content_type="application/json"
            )
        return response

    def verify(self, email, code):
        return self.client.post(
            reverse("verify-email"),
            {"email": email, "code": code},
            content_type="application/json",
        )

    @staticmethod
    def code_from_outbox():
        """Pull the 6-digit code out of the most recent email."""
        return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)

    def test_register_creates_inactive_user_and_sends_code(self):
        response = self.register()

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email=REGISTER_PAYLOAD["email"])
        self.assertFalse(user.is_active)

        otp = user.otps.get()
        self.assertEqual(otp.purpose, EmailVerificationOTP.PURPOSE.REGISTRATION)
        self.assertFalse(otp.is_used)
        # `attempts` is seeded to 5 and counts DOWN (attempts remaining).
        self.assertEqual(otp.attempts, 5)

        # The code must never be stored in the clear.
        self.assertNotIn(self.code_from_outbox(), otp.hashed_code)
        self.assertTrue(otp.hashed_code.startswith("pbkdf2_"))

    def test_verify_with_correct_code_activates_user(self):
        """Regression: this path used to 500 on `otp_record.code` (field removed
        by the hashing migration) and then on `otp_record.is_used()` (a bool)."""
        self.register()
        code = self.code_from_outbox()

        response = self.verify(REGISTER_PAYLOAD["email"], code)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.get(email=REGISTER_PAYLOAD["email"]).is_active)

    def test_verify_with_wrong_code_is_rejected(self):
        self.register()
        wrong = "000000" if self.code_from_outbox() != "000000" else "111111"

        response = self.verify(REGISTER_PAYLOAD["email"], wrong)

        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.json())
        self.assertFalse(User.objects.get(email=REGISTER_PAYLOAD["email"]).is_active)

    def test_verify_with_expired_code_is_rejected(self):
        self.register()
        code = self.code_from_outbox()
        EmailVerificationOTP.objects.update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        response = self.verify(REGISTER_PAYLOAD["email"], code)

        self.assertEqual(response.status_code, 400)
        self.assertIn("expired", str(response.json()["code"]).lower())

    # ----- step 5: templated email -----

    def test_verification_email_is_multipart_with_html_alternative(self):
        self.register()
        message = mail.outbox[-1]

        self.assertEqual(len(message.alternatives), 1)
        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn("<!DOCTYPE html", html)

        # The code must appear in BOTH parts, or text-only clients see nothing.
        code = self.code_from_outbox()
        self.assertIn(code, html)
        self.assertIn(code, message.body)

    def test_verification_email_renders_context(self):
        with override_settings(SITE_NAME="Test Clinic", OTP_TTL_MINUTES=7):
            self.register()

        message = mail.outbox[-1]
        html = message.alternatives[0][0]

        self.assertIn("Test Clinic", message.subject)
        self.assertIn("Test Clinic", html)
        self.assertIn(REGISTER_PAYLOAD["full_name"], html)
        self.assertIn("7 minutes", html)
        self.assertEqual(message.to, [REGISTER_PAYLOAD["email"]])

        # No unrendered template syntax left behind.
        self.assertNotIn("{{", html)
        self.assertNotIn("{{", message.body)

    # ----- step 4: attempt budget + is_used lifecycle -----

    def test_wrong_code_spends_one_attempt(self):
        self.register()
        wrong = "000000" if self.code_from_outbox() != "000000" else "111111"

        self.verify(REGISTER_PAYLOAD["email"], wrong)

        otp = EmailVerificationOTP.objects.get()
        self.assertEqual(otp.attempts, 4)
        self.assertFalse(otp.is_used)

    @override_settings(OTP_MAX_ATTEMPTS=3)
    def test_code_is_burned_after_the_attempt_budget_runs_out(self):
        self.register()
        code = self.code_from_outbox()
        wrong = "000000" if code != "000000" else "111111"

        for _ in range(3):
            response = self.verify(REGISTER_PAYLOAD["email"], wrong)
            self.assertEqual(response.status_code, 400)

        otp = EmailVerificationOTP.objects.get()
        self.assertEqual(otp.attempts, 0)
        self.assertTrue(otp.is_used)

        # Even the CORRECT code must be dead once the budget is exhausted.
        response = self.verify(REGISTER_PAYLOAD["email"], code)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.get(email=REGISTER_PAYLOAD["email"]).is_active)

    def test_attempts_are_seeded_from_settings(self):
        with override_settings(OTP_MAX_ATTEMPTS=9):
            self.register()

        self.assertEqual(EmailVerificationOTP.objects.get().attempts, 9)

    def test_successful_verification_keeps_the_row_and_flags_it_used(self):
        """Regression: the view used to delete() the row, so `is_used` was dead
        weight and the verification history was lost."""
        self.register()

        self.verify(REGISTER_PAYLOAD["email"], self.code_from_outbox())

        otp = EmailVerificationOTP.objects.get()  # still there, not deleted
        self.assertTrue(otp.is_used)

    def test_verify_twice_fails_the_second_time(self):
        self.register()
        code = self.code_from_outbox()

        self.assertEqual(self.verify(REGISTER_PAYLOAD["email"], code).status_code, 200)
        self.assertEqual(self.verify(REGISTER_PAYLOAD["email"], code).status_code, 400)

    def test_verify_for_user_without_code_does_not_crash(self):
        """Regression: .first() returns None, so the old `except DoesNotExist`
        never fired and the next line raised AttributeError on None."""
        User.objects.create_user(
            email="nocode@example.com",
            phone_number="+998901111111",
            password="supersecret1",
            full_name="No Code",
        )

        response = self.verify("nocode@example.com", "123456")

        self.assertEqual(response.status_code, 400)

    def test_latest_code_wins_when_several_exist(self):
        """Regression: `.first()` with no Meta.ordering returned the OLDEST row,
        so after a resend the stale code would have been validated instead."""
        self.register()
        user = User.objects.get(email=REGISTER_PAYLOAD["email"])
        _, newer_code = EmailVerificationOTP.create_code(user)

        self.assertEqual(
            self.verify(REGISTER_PAYLOAD["email"], newer_code).status_code, 200
        )

    def test_otp_ttl_comes_from_settings(self):
        user = User.objects.create_user(
            email="ttl@example.com",
            phone_number="+998902222222",
            password="supersecret1",
            full_name="TTL",
        )
        with override_settings(OTP_TTL_MINUTES=45):
            otp, _ = EmailVerificationOTP.create_code(user)

        self.assertAlmostEqual(
            (otp.expires_at - timezone.now()).total_seconds(), 45 * 60, delta=10
        )

    def test_create_code_accepts_purpose(self):
        user = User.objects.create_user(
            email="reset@example.com",
            phone_number="+998903333333",
            password="supersecret1",
            full_name="Reset",
        )
        otp, _ = EmailVerificationOTP.create_code(
            user, purpose=EmailVerificationOTP.PURPOSE.PASSWORD_RESET
        )

        self.assertEqual(otp.purpose, EmailVerificationOTP.PURPOSE.PASSWORD_RESET)
