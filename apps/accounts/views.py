from django.shortcuts import render
from .models import User, EmailVerificationOTP
from .serializers import UserRegistrationSerializer, EmailVerificationSerializer
from django.core.mail import send_mail
from django.views import View
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import GenericAPIView
# from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.db import transaction  # CHANGE #11 (step 4)
# Create your views here.

# class RegistrationView(View):
#     def post(self, request):
#         user = User.objects.create_user(
#             email=request.POST.get('email'),
#             password=request.POST.get('password'),
#             phone_number=request.POST.get('phone_number'),
#             username=request.POST.get('username'),
#             full_name=request.POST.get('full_name'),
#         )
#         otp_record = EmailVerificationOTP.objects.create(user=user)
#         send_mail(
#             subject="Verify Your Email Address",
#             message="Verification code: " + otp_record.code,
#             from_email="mir.khamroev@gmail.com",
#             recipient_list=[user.email],
#             fail_silently=False
#         )
#         return JsonResponse({'message': 'Verification email dispatched successfully.'})
#
# class EmailVerificationView(View):
#     def post(self, request):
#         email = request.POST.get('email')
#         submitted_code = request.POST.get('code')
#
#         try:
#             user = User.objects.get(email=email)
#             otp_record = user.otp
#             if otp_record.code == submitted_code:
#                 user.is_active = True
#                 user.save()
#                 otp_record.delete()
#                 return JsonResponse({'message': 'Email verified successfully.'}, status=200)
#
#             return JsonResponse({'message': 'Invalid verification code.'}, status=400)
#         except (User.DoesNotExist, EmailVerificationOTP.DoesNotExist):
#             return JsonResponse({'message' : 'Invalid verification request.'}, status=400)



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