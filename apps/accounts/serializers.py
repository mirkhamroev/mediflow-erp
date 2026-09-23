from rest_framework import serializers
from django.contrib.auth.hashers import check_password
from .models import User, EmailVerificationOTP
from apps.commons.validators import validate_email, validate_phone_number, image_size_validator
from .tasks import send_async_email, send_verification_email  # CHANGE #14 (step 5)
from django.db import transaction
from rest_framework.validators import UniqueValidator

class UserRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        validators=[validate_email]
        )
    phone_number = serializers.CharField(
        validators=[validate_phone_number]
        )
    password = serializers.CharField(
        write_only=True, 
        min_length=8
        )

    class Meta:
        model = User
        fields = ['email', 'phone_number', 'password', 'full_name']

    def create(self, validated_data):
        # ===== CHANGE #1 (step 3): whole body wrapped in `with transaction.atomic()`.
        # Without a real transaction the user row was committed even if OTP creation
        # blew up, and `on_commit` had nothing to hook onto (in autocommit mode it
        # fires immediately, which defeats the point). =====
        with transaction.atomic():
            user = User.objects.create_user(
                email=validated_data['email'],
                phone_number=validated_data['phone_number'],
                password=validated_data['password'],
                full_name=validated_data['full_name']
            )
            # ===== CHANGE #2 (step 3): pass `purpose` explicitly now that create_code
            # accepts it, so the same table can serve password-reset / email-change. =====
            _, plain_code = EmailVerificationOTP.create_code(
                user, purpose=EmailVerificationOTP.PURPOSE.REGISTRATION
            )

            # ===== CHANGE #3 (step 3): `transaction.atomic(lambda: ...)` -> `transaction.on_commit(...)`.
            # `transaction.atomic(fn)` treats fn as something to DECORATE: it returns a
            # wrapped callable and never invokes it, so NO email was ever queued.
            # `on_commit` defers the enqueue until the surrounding atomic block commits,
            # so a rolled-back registration sends no mail. =====
            # ===== CHANGE #14 (step 5): send the templated email instead of the
            # hand-built f-string body. Subject and copy now live in the task /
            # templates rather than being duplicated at every call site. =====
            transaction.on_commit(lambda: send_verification_email.delay(
                recipient_email=user.email,
                code=plain_code,
                full_name=user.full_name,
            ))

        return user


# ===== CHANGE #20 (step 6): UserUpdateSerializer removed, replaced by
# UserProfileSerializer + EmailChangeRequestSerializer + EmailChangeConfirmSerializer.
# It wrote the new email to the user BEFORE it was verified (typo / hijacked session
# = account takeover), and the EMAIL_CHANGE code it sent could not be confirmed by
# any endpoint. Its redeclared `email` / `phone_number` fields also dropped the model
# validators (validate_phone_number, max_length=20). =====


class EmailVerificationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)

    class Meta:
        model = EmailVerificationOTP
        fields = ["email", "code"]

    def validate(self, attrs):
        email = attrs.get('email')
        code = attrs.get('code')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User with this email does not exist."})

        try:
            otp_record = user.otps.filter(purpose=EmailVerificationOTP.PURPOSE.REGISTRATION, is_used=False).order_by('-created_at').first()
            if not otp_record:
                raise serializers.ValidationError({"code": "No active verification code found for this user."})
        except EmailVerificationOTP.DoesNotExist:
            raise serializers.ValidationError({"code": "No active verification code found for this user."})


        if otp_record.is_expired():
            raise serializers.ValidationError({
                "code" : "Verification code has expired."
            })
        
        # ===== CHANGE #4 (step 1): compare with check_password() against `hashed_code`.
        # The old line read `otp_record.code`, a field that no longer exists after the
        # hashing migration -> AttributeError -> HTTP 500 on every verify attempt.
        # Also dropped `otp_record.is_used()`: `is_used` is a BooleanField, not a method,
        # so calling it raises TypeError -- and the queryset above already filters
        # is_used=False, making the check redundant anyway.
        # check_password() is constant-time, so no separate compare_digest is needed. =====
        # ===== CHANGE #10 (step 4): a wrong guess now costs one attempt.
        # Without this the endpoint accepted unlimited guesses against a 6-digit code.
        # register_failed_attempt() decrements in the DB and burns the record at 0. =====
        if not check_password(code, otp_record.hashed_code):
            remaining = otp_record.register_failed_attempt()
            if remaining == 0:
                raise serializers.ValidationError({
                    "code": "Too many incorrect attempts. This code is no longer valid, "
                            "please request a new one."
                })
            raise serializers.ValidationError({
                "code": f"Invalid verification code. {remaining} attempt(s) remaining."
            })

        # ----- OLD CODE (before step 1) -----
        # if otp_record.code != code:                                    # AttributeError: no 'code' field
        #     raise serializers.ValidationError({"code": "Invalid verification code."})
        #
        # ----- OLD CODE (intermediate version) -----
        # if not check_password(code, otp_record.hashed_code) or otp_record.is_used():   # TypeError: bool not callable
        #     raise serializers.ValidationError({"code": "Invalid verification code."})
        attrs['user'] = user
        attrs['otp_record'] = otp_record
        return attrs

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
