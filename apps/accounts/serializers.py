from rest_framework import serializers
from django.contrib.auth.hashers import check_password, make_password
from .models import User, EmailVerificationOTP, PendingRegistration
from apps.commons.validators import validate_email, validate_phone_number, image_size_validator
from .tasks import send_async_email, send_verification_email  # CHANGE #14 (step 5)
from django.db import IntegrityError, transaction
from rest_framework.validators import UniqueValidator

# ===== CHANGE #34 (step 7): registration no longer creates a User. It stores the sign-up in
# PendingRegistration and emails a code; the User is created by EmailVerificationSerializer.
# Plain Serializer instead of ModelSerializer(User): the redeclared email/phone fields had
# dropped the unique checks, so a taken email/phone hit an IntegrityError -> HTTP 500. =====
class UserRegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField(
        validators=[validate_email]
        )
    phone_number = serializers.CharField(
        max_length=20,
        validators=[validate_phone_number]
        )
    password = serializers.CharField(
        write_only=True,
        min_length=8
        )
    full_name = serializers.CharField(max_length=255)

    def validate_email(self, value):
        """
        Normalize like UserManager does and reject emails that already belong to a User.
        Pending sign-ups don't count: registering again just replaces the pending one.
        """
        value = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone_number(self, value):
        """Reject phone numbers that already belong to a User (the column is unique)."""
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return value

    def create(self, validated_data):
        """
        Save the sign-up as a PendingRegistration and queue the verification email.
        on_commit: the email is only sent if the pending row was actually written.
        """
        with transaction.atomic():
            pending, plain_code = PendingRegistration.start(
                email=validated_data['email'],
                phone_number=validated_data['phone_number'],
                full_name=validated_data['full_name'],
                raw_password=validated_data['password'],
            )
            transaction.on_commit(lambda: send_verification_email.delay(
                recipient_email=pending.email,
                code=plain_code,
                full_name=pending.full_name,
            ))
        return pending


# ===== CHANGE #20 (step 6): UserUpdateSerializer removed, replaced by
# UserProfileSerializer + EmailChangeRequestSerializer + EmailChangeConfirmSerializer.
# It wrote the new email to the user BEFORE it was verified (typo / hijacked session
# = account takeover), and the EMAIL_CHANGE code it sent could not be confirmed by
# any endpoint. Its redeclared `email` / `phone_number` fields also dropped the model
# validators (validate_phone_number, max_length=20). =====


# ===== CHANGE #35 (step 7): verifies the code against PendingRegistration and creates the
# User on success. Previously it looked up an existing (inactive) User and activated it. =====
class EmailVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        """
        Check the code for the pending sign-up of this email. A wrong code spends one
        attempt (see CHANGE #10); at 0 attempts or after expiry a resend is required.
        """
        email = User.objects.normalize_email(attrs['email'])
        pending = PendingRegistration.objects.filter(email__iexact=email).first()
        if not pending:
            raise serializers.ValidationError({"email": "No pending registration for this email. Please register first."})

        if pending.attempts == 0:
            raise serializers.ValidationError({
                "code": "Too many incorrect attempts. Please request a new code."
            })

        if pending.is_expired():
            raise serializers.ValidationError({"code": "Verification code has expired."})

        if not check_password(attrs['code'], pending.hashed_code):
            remaining = pending.register_failed_attempt()
            if remaining == 0:
                raise serializers.ValidationError({
                    "code": "Too many incorrect attempts. This code is no longer valid, "
                            "please request a new one."
                })
            raise serializers.ValidationError({
                "code": f"Invalid verification code. {remaining} attempt(s) remaining."
            })

        attrs['pending'] = pending
        return attrs

    def save(self):
        """
        Create the active User from the pending sign-up. If the email/phone was taken
        between registration and verification, the insert fails, the transaction rolls
        back (the pending row is kept) and the client gets a 400 instead of a 500.
        """
        pending = self.validated_data['pending']
        try:
            with transaction.atomic():
                return pending.complete()
        except IntegrityError:
            raise serializers.ValidationError({
                "email": "This email or phone number has already been registered."
            })


# ===== CHANGE #36 (step 7): resend only works for a pending sign-up. It used to issue a
# REGISTRATION code for ANY User, which let deactivated users re-activate themselves. =====
class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        """Find the pending sign-up for this email; existing Users are never touched."""
        value = User.objects.normalize_email(value)
        pending = PendingRegistration.objects.filter(email__iexact=value).first()
        if not pending:
            raise serializers.ValidationError("No pending registration for this email.")
        self.context['pending'] = pending
        return value

    def save(self):
        """Replace the code (old one stops working, attempts reset) and email the new one."""
        pending = self.context['pending']
        with transaction.atomic():
            plain_code = pending.issue_code()
            transaction.on_commit(lambda: send_verification_email.delay(
                recipient_email=pending.email,
                code=plain_code,
                full_name=pending.full_name,
            ))
        return pending

# ===== CHANGE #21 (step 6): profile fields that need no verification.
# `phone_number` is NOT redeclared, so ModelSerializer keeps the model's
# validate_phone_number, max_length=20 and an auto UniqueValidator.
# `email` and `role` are read-only: email goes through the change/confirm flow,
# role must never be self-assigned. =====
class UserProfileSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(allow_null=True, validators=[image_size_validator])
    class Meta:
        model = User
        fields = [ 'id', 'email', 'phone_number', 'full_name', 'image', 'role' ]
        read_only_fields = ['id', 'email', "role"]

    def update(self, instance, validated_data):
        # Delete the old file from storage when the image is replaced or cleared,
        # otherwise media/user_images/ fills up with orphaned files.
        if 'image' in validated_data and instance.image:
            instance.image.delete(save=False)
        return super().update(instance, validated_data)

# ===== CHANGE #22 (step 6): step 1 of the email change -- only sends a code to the
# new address; the user's email is not touched until EmailChangeConfirmSerializer. =====
class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField(validators=[validate_email])
    # CHANGE #22 (step 6): `min_lenght` -> removed. The typo raised TypeError when the
    # module was imported, so the whole app failed to start. A length rule is
    # pointless here anyway -- this field is compared to the existing password.
    password = serializers.CharField(write_only=True)
    # ----- OLD CODE -----
    # password = serializers.CharField(write_only=True, min_lenght=8)

    def validate_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError("Incorrect password.")
        return value

    def validate_new_email(self, value):
        # CHANGE #22 (step 6): normalize_email() (lowercases the domain only) instead of
        # .lower() -- same normalization UserManager uses at registration. Login matches
        # the email exactly, so a different rule here could lock the user out.
        value = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already in use.")
        return value
        # ----- OLD CODE -----
        # return value.lower()  # Normalize to lowercase for consistency

    def save(self):
        user = self.context['request'].user
        new_email = self.validated_data['new_email']
        with transaction.atomic():
            user.otps.filter(purpose=EmailVerificationOTP.PURPOSE.EMAIL_CHANGE, is_used=False).update(is_used=True)
            otp_record, plain_code = EmailVerificationOTP.create_code(
                user, purpose=EmailVerificationOTP.PURPOSE.EMAIL_CHANGE, new_email=new_email
            )
            transaction.on_commit(lambda: send_verification_email.delay(
                recipient_email=new_email,
                code=plain_code,
                full_name=user.full_name,
            ))

            return user

# ===== CHANGE #23 (step 6): step 2 of the email change -- verifies the code, then
# swaps the email. Now checks the same things EmailVerificationSerializer does. =====
class EmailChangeConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        user = self.context['request'].user
        otp = (user.otps.filter(purpose=EmailVerificationOTP.PURPOSE.EMAIL_CHANGE, is_used=False)
                .order_by('-created_at').first())
        if not otp:
            raise serializers.ValidationError({"code": "No active verification code found for this user."})

        # CHANGE #23 (step 6): expiry check was missing -- an old code stayed valid forever.
        if otp.is_expired():
            raise serializers.ValidationError({"code": "Verification code has expired."})

        # CHANGE #23 (step 6): a wrong guess now costs an attempt (see CHANGE #10).
        # Without it the 6-digit code could be brute-forced with unlimited guesses.
        if not check_password(attrs['code'], otp.hashed_code):
            remaining = otp.register_failed_attempt()
            if remaining == 0:
                raise serializers.ValidationError({
                    "code": "Too many incorrect attempts. This code is no longer valid, "
                            "please request a new one."
                })
            raise serializers.ValidationError({
                "code": f"Invalid verification code. {remaining} attempt(s) remaining."
            })
        # ----- OLD CODE -----
        # if not check_password(attrs['code'], otp.hashed_code):
        #     raise serializers.ValidationError({"code": "Invalid verification code."})

        # CHANGE #23 (step 6): exclude the current user so re-confirming your own address
        # is not reported as "in use"; someone else may still have taken it since the request.
        if User.objects.filter(email__iexact=otp.new_email).exclude(pk=user.pk).exists():
            raise serializers.ValidationError({"code": "This email is already in use."})
        # ----- OLD CODE -----
        # if User.objects.filter(email__iexact=otp.new_email).exists():
        attrs['otp_record'] = otp
        return attrs

    def save(self):
        user = self.context['request'].user
        otp_record = self.validated_data['otp_record']
        with transaction.atomic():
            user.email = otp_record.new_email
            # CHANGE #23 (step 6): fixed the stray `])])` -- a SyntaxError that stopped the
            # module (and the whole project) from importing.
            user.save(update_fields=["email", "updated_at"])
            # ----- OLD CODE -----
            # user.save(update_fields=["email", 'updated_at'])])
            otp_record.mark_used()
        return user


class ResetPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(validators=[validate_email])
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        # CHANGE #24 (step 6): normalize_email() (lowercases the domain only) instead of
        # .lower() -- same normalization UserManager uses at registration. Login matches
        # the email exactly, so a different rule here could lock the user out.
        value = User.objects.normalize_email(value)
        if not User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return value

    def save(self):
        email = self.validated_data['email']
        password = self.validated_data['password']
        user = User.objects.get(email__iexact=email)
        with transaction.atomic():
            user.otps.filter(purpose=EmailVerificationOTP.PURPOSE.PASSWORD_RESET, is_used=False).update(is_used=True)
            otp_record, plain_code = EmailVerificationOTP.create_code(
                # Store the hash, not the plaintext, so the pending password
                # is never readable from the otp table.
                user, purpose=EmailVerificationOTP.PURPOSE.PASSWORD_RESET,
                new_password=make_password(password)
            )
            transaction.on_commit(lambda: send_verification_email.delay(
                recipient_email=email,
                code=plain_code,
                full_name=user.full_name
            ))

            return user

class ResetPasswordConfirmSerializer(serializers.Serializer):
    # `email` is a declared field so a missing one fails with "This field is
    # required." instead of a misleading "user does not exist" from validate().
    email = serializers.EmailField(validators=[validate_email])
    code = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        try:
            user = User.objects.get(email__iexact=attrs['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User with this email does not exist."})

        otp_record = (user.otps.filter(purpose=EmailVerificationOTP.PURPOSE.PASSWORD_RESET, is_used=False)
                      .order_by('-created_at').first())
        if not otp_record:
            raise serializers.ValidationError({"code": "No active verification code found for this user."})

        if otp_record.is_expired():
            raise serializers.ValidationError({"code": "Verification code has expired."})

        if not check_password(attrs['code'], otp_record.hashed_code):
            remaining = otp_record.register_failed_attempt()
            if remaining == 0:
                raise serializers.ValidationError({
                    "code": "Too many incorrect attempts. This code is no longer valid, "
                            "please request a new one."
                })
            raise serializers.ValidationError({
                "code": f"Invalid verification code. {remaining} attempt(s) remaining."
            })

        attrs['user'] = user
        attrs['otp_record'] = otp_record
        return attrs

    def save(self):
        user = self.validated_data['user']
        otp_record = self.validated_data['otp_record']
        with transaction.atomic():
            # new_password is already hashed at request time; assign directly.
            user.password = otp_record.new_password
            user.save(update_fields=["password", "updated_at"])
            otp_record.mark_used()
        return user