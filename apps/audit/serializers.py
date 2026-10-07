from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """
    Read-only representation of an audit entry. All fields are read-only because the
    API never accepts writes; entries are created by apps.audit.services.log_action.
    """
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'timestamp', 'action', 'action_display', 'user', 'username', 'user_role',
                  'model_name', 'object_id', 'object_repr', 'old_values', 'new_values',
                  'ip_address', 'user_agent']
        read_only_fields = fields
