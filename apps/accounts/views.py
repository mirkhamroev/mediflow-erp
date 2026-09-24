from django.shortcuts import render
from .models import User, EmailVerificationOTP
# CHANGE #24 (step 6): dropped UserUpdateSerializer (removed), added EmailChangeRequestSerializer
from .serializers import (UserRegistrationSerializer, EmailVerificationSerializer,
                          UserProfileSerializer, EmailChangeRequestSerializer, EmailChangeConfirmSerializer)
# ----- OLD CODE -----
# from .serializers import (UserRegistrationSerializer, EmailVerificationSerializer, UserUpdateSerializer,
#                           UserProfileSerializer, EmailChangeConfirmSerializer)
from django.core.mail import send_mail
from django.views import View
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import GenericAPIView, RetrieveUpdateDestroyAPIView
# from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db import transaction  # CHANGE #11 (step 4)
from .tasks import send_verification_email  # CHANGE #14 (step 5)
from rest_framework.parsers import MultiPartParser, FormParser

# Create your views here.



class RegisterAPIView(GenericAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    #@swagger_auto_schema(request_body=UserRegistrationSerializer)
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Registration successful. Please check your email for verification code."},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ===== CHANGE #25 (step 6): UserDetailAPIView removed, replaced by MeAPIView.
# It used UserUpdateSerializer (unverified email change) and allowed PUT + hard DELETE. =====
# ----- OLD CODE (before step 6) -----
# class UserDetailAPIView(RetrieveUpdateDestroyAPIView):
#     queryset = User.objects.all()
#     serializer_class = UserUpdateSerializer
#     permission_classes = [IsAuthenticated]
#
#     def get_object(self):
#         return self.request.user

# ===== CHANGE #26 (step 6): GET / PATCH / DELETE on the logged-in user's own profile. =====
class MeAPIView(RetrieveUpdateDestroyAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # Allow file uploads for the image field
    http_method_names = ['get', 'patch', 'delete']  # no PUT: partial updates only

    def get_object(self):
        return self.request.user

    def patch(self, request, *args, **kwargs):
        # Only allow updating certain fields (e.g., full_name, phone_number, image)
        allowed_fields = ['full_name', 'phone_number', 'image']
        data = {field: request.data[field] for field in allowed_fields if field in request.data}
        if data.get('image') == '':
            # An untouched file input in a multipart form arrives as ''; treat it
            # as "clear the image" (serializer has allow_null=True).
            data['image'] = None
        serializer = self.get_serializer(self.get_object(), data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def perform_destroy(self, instance):
        # Instead of deleting the user, we can deactivate the account
        instance.is_active = False
        # CHANGE #26 (step 6): update_fields so a plain save() can't overwrite other
        # columns with stale in-memory values. JWTAuthentication rejects inactive users,
        # so existing tokens stop working immediately.
        instance.save(update_fields=["is_active", "updated_at"])
        # ----- OLD CODE -----
        # instance.save()

# ===== CHANGE #27 (step 6): step 1 of the email change (send code to the new address). =====
class EmailChangeRequestAPIView(GenericAPIView):
    # CHANGE #27 (step 6): was EmailVerificationSerializer (the registration verifier) -- it
    # demanded `email` + `code` and then crashed on save() because it has no create().
    serializer_class = EmailChangeRequestSerializer
    # ----- OLD CODE -----
    # serializer_class = EmailVerificationSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        return Response({"message": "Email change request initiated. Please check your new email for verification code."}, status=status.HTTP_200_OK)

# ===== CHANGE #28 (step 6): step 2 of the email change (verify code, swap email). =====
class EmailChangeConfirmAPIView(GenericAPIView):
    serializer_class = EmailChangeConfirmSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        return Response({"message": "Email changed successfully."}, status=status.HTTP_200_OK)


class VerifyEmailAPIView(GenericAPIView):
    serializer_class = EmailVerificationSerializer
    permission_classes = [AllowAny]

    #@swagger_auto_schema(request_body=EmailVerificationSerializer)
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            otp_record = serializer.validated_data['otp_record']

            # ===== CHANGE #11 (step 4): activate + burn inside one transaction.
            # Separate saves could leave a user activated with the code still live
            # (replayable) if the second write failed. =====
            with transaction.atomic():
                # Activate User
                user.is_active = True
                user.save(update_fields=["is_active"])

                # ===== CHANGE #12 (step 4): mark_used() instead of delete().
                # delete() destroyed the audit trail and left `is_used` permanently
                # unused; the verification query already filters on is_used=False,
                # so flagging the row is what actually retires the code. =====
                otp_record.mark_used()

            return Response({"message": "Email verified successfully! Account activated."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # ----- OLD CODE (before step 4) -----
        # user.is_active = True
        # user.save()
        #
        # # Burn used code
        # otp_record.delete()          # <-- threw away history; is_used was never set
    # def post(self, request, validated_data=None):
    #     serializer = EmailVerificationSerializer(data=request.data)
    #     if serializer.is_valid():
    #         user = serializer.validated_data['user']
    #         otp_record = serializer.validated_data['otp_record']

    #         # Activate User
    #         user.is_active = True
    #         user.save()

    #         # Burn used code
    #         otp_record.delete()

    #         return Response({"message": "Email verified successfully! Account activated."}, status=status.HTTP_200_OK)
    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResendVerificationEmailAPIView(GenericAPIView):
    serializer_class = EmailVerificationSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        try:
            user = User.objects.get(email=email)
            otp_record, plain_code = EmailVerificationOTP.create_code(user)

            # Send the verification email asynchronously
            transaction.on_commit(lambda: send_verification_email.delay(
                recipient_email=user.email,
                code=plain_code,
                full_name=user.full_name,
            ))

            return Response({"message": "Verification email resent successfully."}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User with this email does not exist."}, status=status.HTTP_400_BAD_REQUEST)