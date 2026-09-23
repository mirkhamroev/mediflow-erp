from rest_framework.routers import DefaultRouter
# CHANGE #29 (step 6): UserDetailAPIView -> MeAPIView + email-change + resend views
from .views import (RegisterAPIView, VerifyEmailAPIView, ResendVerificationEmailAPIView,
                    MeAPIView, EmailChangeRequestAPIView, EmailChangeConfirmAPIView)
# ----- OLD CODE -----
# from .views import RegisterAPIView, VerifyEmailAPIView, UserDetailAPIView
# CHANGE #30 (step 6): JWT login / refresh -- settings use JWTAuthentication but no
# endpoint issued tokens, so no IsAuthenticated view could ever be reached.
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.urls import path, include

# router = DefaultRouter()
# router.register(r'register', RegisterAPIView, basename='register')
# router.register(r'verify-email', VerifyEmailAPIView, basename='verify-email')


# urlpatterns = router.urls

urlpatterns = [
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('verify-email/', VerifyEmailAPIView.as_view(), name='verify-email'),
    # CHANGE #31 (step 6): pointed at RegisterAPIView, so "resend" tried to register again.
    path('resend-verification-email/', ResendVerificationEmailAPIView.as_view(), name='resend-verification-email'),
    # ----- OLD CODE -----
    # path('resend-verification-email/', RegisterAPIView.as_view(), name='resend-verification-email'),
    # CHANGE #30 (step 6): POST {email, password} -> {access, refresh}
    path('token/', TokenObtainPairView.as_view(), name='token-obtain'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    # CHANGE #29 (step 6): own-profile + two-step email change
    path('me/', MeAPIView.as_view(), name='me'),
    path('me/email/', EmailChangeRequestAPIView.as_view(), name='email-change'),
    path('me/email/confirm/', EmailChangeConfirmAPIView.as_view(), name='email-change-confirm'),
    # ----- OLD CODE -----
    # path('user-details/', UserDetailAPIView.as_view(), name='user-details'),
]
