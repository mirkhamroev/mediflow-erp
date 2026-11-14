from django.shortcuts import render
from .models import User, EmailVerificationOTP
# CHANGE #24 (step 6): dropped UserUpdateSerializer (removed), added EmailChangeRequestSerializer
from .serializers import (UserRegistrationSerializer, EmailVerificationSerializer, ResendVerificationSerializer,
                          UserProfileSerializer, EmailChangeRequestSerializer, EmailChangeConfirmSerializer, 
                          ResetPasswordRequestSerializer, ResetPasswordConfirmSerializer)
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
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

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
    # JSONParser must stay: multipart handles the image upload, but plain
    # profile updates (name, phone) arrive as JSON.
    parser_classes = [MultiPartParser, FormParser, JSONParser]
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

    # ===== CHANGE #37 (step 7): a correct code now CREATES the user from the pending
    # sign-up (EmailVerificationSerializer.save). It used to activate an inactive User,
    # which required storing every unconfirmed sign-up as a User row. =====
    def post(self, request):
        """Verify {email, code}; on success the account exists and can log in."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Email verified successfully! Account created."}, status=status.HTTP_201_CREATED)


class ResendVerificationEmailAPIView(GenericAPIView):
    # ===== CHANGE #38 (step 7): only pending sign-ups can get a new code (see CHANGE #36). =====
    serializer_class = ResendVerificationSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        """Send a fresh code for a pending sign-up {email}."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Verification email resent successfully."}, status=status.HTTP_200_OK)

class PasswordResetRequestAPIView(GenericAPIView):
    serializer_class = ResetPasswordRequestSerializer
    # AllowAny: a user who forgot their password cannot authenticate.
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Password reset request initiated. Please check your email for verification code."}, status=status.HTTP_200_OK)

from rest_framework_simplejwt.views import TokenObtainPairView, TokenBlacklistView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from apps.audit.services import log_action


class PasswordResetConfirmAPIView(GenericAPIView):
    serializer_class = ResetPasswordConfirmSerializer
    # AllowAny: a user who forgot their password cannot authenticate.
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Password reset successfully."}, status=status.HTTP_200_OK)


class AuditedTokenObtainPairView(TokenObtainPairView):
    """
    Issues a JWT pair and records a LOGIN entry in the audit trail.
    """
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.user
        log_action(action='login', instance=user, user=user, request=request)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class AuditedTokenBlacklistView(TokenBlacklistView):
    """
    Blacklists a refresh token (logout) and records a LOGOUT entry in the audit trail.
    TokenBlacklistView is AllowAny by default, so we resolve the user from the refresh
    token payload if request.user is anonymous.
    """
    def post(self, request, *args, **kwargs):
        user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
        if user is None:
            raw_refresh = request.data.get('refresh')
            if raw_refresh:
                try:
                    token = RefreshToken(raw_refresh)
                    user_id = token.payload.get('user_id')
                    if user_id:
                        user = User.objects.filter(pk=user_id).first()
                except TokenError:
                    pass

        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            log_action(
                action='logout',
                instance=user,
                model_name='accounts.User',
                user=user,
                request=request,
            )
        return response