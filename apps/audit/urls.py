from .views import AuditLogViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'logs', AuditLogViewSet, basename='audit-log')


urlpatterns = router.urls
