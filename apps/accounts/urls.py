from rest_framework.routers import DefaultRouter
from .views import RegisterAPIView, VerifyEmailAPIView
from django.urls import path, include

# router = DefaultRouter()
# router.register(r'register', RegisterAPIView, basename='register')
# router.register(r'verify-email', VerifyEmailAPIView, basename='verify-email')


# urlpatterns = router.urls

urlpatterns = [
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('verify-email/', VerifyEmailAPIView.as_view(), name='verify-email'),
]