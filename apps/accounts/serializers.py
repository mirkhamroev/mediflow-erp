from rest_framework import serializers
from django.contrib.auth.hashers import check_password
from .models import User, EmailVerificationOTP
from apps.commons.validators import validate_email, validate_phone_number
from .tasks import send_async_email, send_verification_email  # CHANGE #14 (step 5)
from django.db import transaction

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

            # ----- OLD CODE (before step 5) -----
            # transaction.on_commit(lambda: send_async_email.delay(
            #     subject="Verify Your Email!",
            #     message=f"Your registration code : {plain_code}",
            #     recipient_email=user.email
            # ))
        return user

        # ----- OLD CODE (before step 3) -----
        # user = User.objects.create_user(
        #     # username="",
        #     email=validated_data['email'],
        #     phone_number=validated_data['phone_number'],
        #     password=validated_data['password'],
        #     full_name=validated_data['full_name']
        # )
        # _, plain_code = EmailVerificationOTP.create_code(user)
        #
        # transaction.atomic(lambda: send_async_email.delay(   # <-- never executed the lambda
        #     subject="Verify Your Email!",
        #     message=f"Your registration code : {plain_code}",
        #     recipient_email=user.email
        # ))
        # return user

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
