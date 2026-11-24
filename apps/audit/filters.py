import django_filters

from .models import AuditLog


class AuditLogFilter(django_filters.FilterSet):
    """
    Query-string filters for the audit log list, e.g.
        ?model_name=clinical.Prescription&object_id=<uuid>   -> full history of one object
        ?user=<uuid>&date_from=2026-10-01                    -> what a user did since a date
        ?action=update&action=delete                         -> several actions at once
    """
    action = django_filters.MultipleChoiceFilter(choices=AuditLog.ACTION_CHOICES)
    date_from = django_filters.IsoDateTimeFilter(field_name='timestamp', lookup_expr='gte')
    date_to = django_filters.IsoDateTimeFilter(field_name='timestamp', lookup_expr='lte')

    class Meta:
        model = AuditLog
        fields = ['action', 'user', 'user_role', 'model_name', 'object_id', 'ip_address']
