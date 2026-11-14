from django.db import models
from django.db.models import F  # CHANGE #9 (step 4): atomic attempt decrement
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser
import uuid
from apps.commons.mixins import AuditableModelMixin
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


class User(AuditableModelMixin, AbstractUser):
    audit_exclude_fields = ('updated_at', 'last_login')
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Administrator"
        ACCOUNTANT = "accountant", "Accountant"
        ADMIN = "admin", "Admin"
        USER = "user", "User"
        DOCTOR = "doctor", "Doctor"
        PATIENT = "patient", "Patient"
        PHARMACIST = "pharmacist", "Pharmacist"
        NURSE = "nurse", "Nurse"
        RECEPTIONIST = "receptionist", "Receptionist"
        INSURANCE_MANAGER = "insurance_manager", "Insurance Manager"

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
        return self.role in (self.Role.ADMIN, self.Role.SUPER_ADMIN) or self.is_superuser

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
    def is_insurance_manager(self):
        return self.role == self.Role.INSURANCE_MANAGER

    @property
    def is_user(self):
        return self.role == self.Role.USER

    def has_role(self, *role_codes):
        """
        True if the user's primary `role` field OR any active `UserRole` assignment
        matches one of `role_codes`. Superusers and super_admins match administrative checks.
        """
        if not self.is_active:
            return False
        if self.role in role_codes:
            return True
        return self.user_roles.filter(
            is_active=True,
            role__is_active=True,
            role__code__in=role_codes,
        ).exists()

    def has_rbac_perm(self, *perm_codes):
        """
        True if the user is a superuser/super_admin, or holds any of `perm_codes`
        (e.g. 'clinical.create_prescription', 'inventory.dispense') via an assigned
        `UserRole` or via the `Role` matching their primary `user.role` code.
        """
        if not self.is_active:
            return False
        if self.is_superuser or self.role == self.Role.SUPER_ADMIN:
            return True
        from django.db.models import Q
        return Role.objects.filter(
            Q(user_roles__user=self, user_roles__is_active=True) | Q(code=self.role),
            is_active=True,
            permissions__code__in=perm_codes,
        ).exists()



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
    # ===== CHANGE #18 (step 6): pending address for EMAIL_CHANGE codes. The user's real
    # `email` is only overwritten after this code is confirmed (migration 0005). =====
    new_email = models.EmailField(null=True, blank=True)  # For email change requests
    new_password = models.CharField(max_length=255, null=True, blank=True)  # For password reset requests
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
    # ===== CHANGE #19 (step 6): new `new_email` parameter. EmailChangeRequestSerializer
    # already passed it, which raised TypeError -> HTTP 500 on every email-change request. =====
    # ===== CHANGE #20 (step 6): new `new_password` parameter. PasswordResetRequestSerializer
    # already passed it, which raised TypeError -> HTTP 500 on every password-reset request. =====
    def create_code(cls, user, purpose=None, new_email=None, new_password=None):
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
            new_email=new_email,  # CHANGE #19 (step 6): stored only for EMAIL_CHANGE codes
            new_password=new_password,  # CHANGE #20 (step 6): stored only for PASSWORD_RESET codes
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

# ===== CHANGE #33 (step 7): sign-up data waits here until the email is confirmed.
# Previously RegisterAPIView created the User (is_active=False) straight away, so an
# unconfirmed sign-up still occupied the unique email/phone (a typo locked the real
# owner out), and "resend verification" could re-activate deactivated accounts.
# Now no User row exists until the OTP is verified; complete() creates it already active. =====
class PendingRegistration(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    # unique: registering the same email again replaces the pending row instead of piling up
    email = models.EmailField(max_length=255, unique=True)
    phone_number = models.CharField(max_length=20)
    full_name = models.CharField(max_length=255)
    password = models.CharField(max_length=255)  # already hashed with make_password, never plaintext
    hashed_code = models.CharField(max_length=255)
    attempts = models.PositiveSmallIntegerField(default=0)  # wrong guesses REMAINING, like EmailVerificationOTP
    expires_at = models.DateTimeField()
    # default (not auto_now_add) so a repeated sign-up can reset it; purge_pending_registrations reads it
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Pending registration"
        verbose_name_plural = "Pending registrations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"pending : {self.email}"

    @staticmethod
    def _fresh_code():
        """
        Generate a new 6-digit code. Returns (plain_code, fields) where fields are the
        hashed code, a new expiry and a full attempt budget, ready to store on the row.
        The plain code only goes into the email, never into the database.
        """
        plain_code = str(secrets.randbelow(1000000)).zfill(6)
        fields = {
            "hashed_code": make_password(plain_code),
            "expires_at": timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES),
            "attempts": settings.OTP_MAX_ATTEMPTS,
        }
        return plain_code, fields

    @classmethod
    def start(cls, *, email, phone_number, full_name, raw_password):
        """
        Store (or overwrite) the sign-up for this email and issue a verification code.
        Overwriting lets someone who mistyped their phone/name, or lost the email,
        simply register again. Returns (pending_registration, plain_code).
        """
        plain_code, code_fields = cls._fresh_code()
        pending, _ = cls.objects.update_or_create(
            email=email,
            defaults={
                "phone_number": phone_number,
                "full_name": full_name,
                "password": make_password(raw_password),
                "created_at": timezone.now(),
                **code_fields,
            },
        )
        return pending, plain_code

    def issue_code(self):
        """
        Replace the current code with a new one (resend). The old code stops working
        immediately because only the latest hash is stored. Returns the plain code.
        """
        plain_code, code_fields = self._fresh_code()
        for field, value in code_fields.items():
            setattr(self, field, value)
        self.save(update_fields=list(code_fields))
        return plain_code

    def is_expired(self):
        """True once the current code's TTL (settings.OTP_TTL_MINUTES) has passed."""
        return self.expires_at < timezone.now()

    def register_failed_attempt(self):
        """
        Spend one attempt after a wrong code and return how many remain. At 0 the code
        is dead and only a resend (new code) can continue the sign-up.
        F() keeps two concurrent wrong guesses from overwriting each other's decrement.
        """
        if self.attempts > 0:
            PendingRegistration.objects.filter(pk=self.pk, attempts__gt=0).update(
                attempts=F("attempts") - 1
            )
            self.refresh_from_db(fields=["attempts"])
        return self.attempts

    def complete(self):
        """
        Turn the verified sign-up into a real, active User and delete this pending row.
        Call inside transaction.atomic(): if the User insert fails (email/phone taken in
        the meantime -> IntegrityError) the pending row must survive.
        The password is already hashed, so it is assigned directly instead of going
        through create_user(), which would hash it a second time.
        """
        user = User(
            email=self.email,
            phone_number=self.phone_number,
            full_name=self.full_name,
            password=self.password,
            is_active=True,
        )
        user.save()
        self.delete()
        return user


# ============================================================
# Phase 2.2 --- RBAC Models (Role, Permission, UserRole)
# ============================================================

class Permission(AuditableModelMixin, models.Model):
    """
    Fine-grained domain permission (e.g. 'clinical.read', 'inventory.dispense').
    Named `Permission` per Phase 2.2 specification, with a distinct `db_table` and
    related names so it never clashes with `django.contrib.auth.models.Permission`.
    """
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    code = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    module = models.CharField(max_length=50, db_index=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "RBAC Permission"
        verbose_name_plural = "RBAC Permissions"
        ordering = ["module", "code"]

    def __str__(self):
        return f"{self.code} ({self.name})"


class Role(AuditableModelMixin, models.Model):
    """
    Named role grouping a set of `Permission` objects (e.g. 'doctor', 'pharmacist').
    """
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(null=True, blank=True)
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class UserRole(AuditableModelMixin, models.Model):
    """
    Explicit assignment of a `Role` to a `User`.
    """
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_user_roles",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Role"
        verbose_name_plural = "User Roles"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="unique_user_role_assignment"),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.role.code}"

