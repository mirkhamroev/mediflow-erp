from django.db import models
from django.db.models import F  # CHANGE #9 (step 4): atomic attempt decrement
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser
import uuid
from apps.commons.validators import validate_email, validate_phone_number
from .managers import UserManager
from django.utils import timezone
from datetime import timedelta
# ===== CHANGE #5 (step 3): use django.conf.settings, not a direct module import.
# `import mediflow_erp.core.settings as settings` fails at startup (the package is
# `core`, there is no `mediflow_erp` package) and would also bypass Django's lazy
# settings object, ignoring DJANGO_SETTINGS_MODULE and any env overrides. =====
from django.conf import settings
# ----- OLD CODE (before step 3) -----
# import mediflow_erp.core.settings as settings
import random, secrets

# Create your models here.


class User(AbstractUser):
    class Role(models.TextChoices):
        ACCOUNTANT = "accountant", "Accountant"
        ADMIN = "admin", "Admin"
        USER = "user", "User"
        DOCTOR = "doctor", "Doctor"
        PATIENT = "patient", "Patient"
        PHARMACIST = "pharmacist", "Pharmacist"
        NURSE = "nurse", "Nurse"
        RECEPTIONIST = "receptionist", "Receptionist"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    email = models.EmailField(max_length=255,unique=True, validators=[validate_email])
    phone_number = models.CharField(max_length=20, unique=True, validators=[validate_phone_number])
    password = models.CharField(max_length=255)
    image = models.ImageField(upload_to='user_images/', null=True, blank=True)
    username = None
    full_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone_number', 'full_name']
    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]

    def __str__(self):
        return f"username : {self.email}, full_name : {self.full_name}"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_accountant(self):
        return self.role == self.Role.ACCOUNTANT

    @property
    def is_patient(self):
        return self.role == self.Role.PATIENT

    @property
    def is_doctor(self):
        return self.role == self.Role.DOCTOR

    @property
    def is_pharmacist(self):
        return self.role == self.Role.PHARMACIST

    @property
    def is_nurse(self):
        return self.role == self.Role.NURSE

    @property
    def is_receptionist(self):
        return self.role == self.Role.RECEPTIONIST

    @property
    def is_user(self):
        return self.role == self.Role.USER


class EmailVerificationOTP(models.Model):
    class PURPOSE(models.TextChoices):
        REGISTRATION = "registration", "Registration"
        PASSWORD_RESET = "password_reset", "Password Reset"
        EMAIL_CHANGE = "email_change", "Email Change"
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    hashed_code = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=5)
    purpose = models.CharField(max_length=20, choices=PURPOSE.choices, default=PURPOSE.REGISTRATION)
    is_used = models.BooleanField(default=False)

    # def save(self, *args, **kwargs):
    #     # super().save(*args, **kwargs)
    #     if not self.hashed_code:
    #         # Below line generates a strong cryptographically secure random 6-digit code
    #         # using secrets module instead of random for better security
    #         self.hashed_code = make_password(str(secrets.randbelow(1000000)).zfill(6))  # Generate a random 6-digit code and hashs it with make_password function
    #     if not self.expires_at:
    #         self.expires_at = timezone.now() + timedelta(minutes=10)
    #     super().save(*args, **kwargs)

    @classmethod
    def create_code(cls, user, purpose=None):
        # ===== CHANGE #6 (step 3): `purpose` is now a parameter.
        # Previously every row fell back to the model default "registration", so the
        # password_reset / email_change choices could never actually be written. =====
        purpose = purpose or cls.PURPOSE.REGISTRATION

        plain_code = str(secrets.randbelow(1000000)).zfill(6)  # Generate a random 6-digit code
        hashed_code = make_password(plain_code)  # Hash the code using Django's make
        expires_at = timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES)

        # ===== CHANGE #8 (step 4): seed `attempts` from settings.OTP_MAX_ATTEMPTS.
        # The field default (5) is baked into a migration, so tuning the limit meant a
        # schema change. Setting it here makes the budget configurable at runtime;
        # `attempts` counts DOWN -- it is the number of tries REMAINING. =====
        otp_record = cls.objects.create(
            user=user,
            hashed_code=hashed_code,
            expires_at=expires_at,
            purpose=purpose,
            attempts=settings.OTP_MAX_ATTEMPTS,
        )
        return otp_record, plain_code  # Return both the OTP record and the plain code for sending in the email

    # ===== CHANGE #9 (step 4): state transitions live on the model, not in the view.
    # Previously the view called otp_record.delete(), which threw away the audit trail
    # and made the `is_used` column dead weight -- it was never written by anything. =====
    def mark_used(self):
        """Burn the code after a successful verification (kept as history)."""
        self.is_used = True
        self.save(update_fields=["is_used"])

    def register_failed_attempt(self):
        """Spend one attempt. Returns the number remaining; burns the code at 0.

        Uses F() so two concurrent wrong guesses can't both read the same value
        and overwrite each other -- the decrement happens in the database.
        """
        if self.attempts > 0:
            EmailVerificationOTP.objects.filter(pk=self.pk, attempts__gt=0).update(
                attempts=F("attempts") - 1
            )
            self.refresh_from_db(fields=["attempts"])

        if self.attempts == 0 and not self.is_used:
            self.mark_used()  # out of budget: this code can never be used again

        return self.attempts

    # ----- OLD CODE (before step 3) -----
    # def create_code(cls, user):
    #     plain_code = str(secrets.randbelow(1000000)).zfill(6)
    #     hashed_code = make_password(plain_code)
    #     expires_at = timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES)
    #     otp_record = cls.objects.create(user=user, hashed_code=hashed_code, expires_at=expires_at)
    #     return otp_record, plain_code


    def is_expired(self):
        return self.expires_at < timezone.now()