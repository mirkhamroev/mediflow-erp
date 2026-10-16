from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from apps.commons.permissions import CanViewAuditLog
from .filters import AuditLogFilter
from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API over the audit trail.

    GET /api/audit/logs/        -> paginated, filterable list (see AuditLogFilter)
    GET /api/audit/logs/<id>/   -> single entry with full old/new values

    ReadOnlyModelViewSet exposes no POST/PUT/PATCH/DELETE routes at all, so the API
    cannot modify the log even if a permission check were misconfigured.
    """
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [CanViewAuditLog]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AuditLogFilter
    search_fields = ['username', 'object_repr', 'object_id']
    ordering_fields = ['timestamp', 'action', 'model_name']
    ordering = ['-timestamp']
