from django.db import models
import uuid
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder


# Create your models here.


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        # Prevent direct updates to AuditLog entries
        raise PermissionDenied("Direct updates to AuditLog entries are not allowed.")

    def delete(self, *args, **kwargs):
        # Prevent direct deletions of AuditLog entries
        raise PermissionDenied("Direct deletions of AuditLog entries are not allowed.")
class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'CREATE'),
        ('update', 'UPDATE'),
        ('delete', 'DELETE'),
        ('view', 'VIEW'),
        ('login', 'LOGIN'),
        ('logout', 'LOGOUT'),
        ('prescribe', 'PRESCRIBE'),
        ('dispense', 'DISPENSE'),
        ('payment', 'PAYMENT'),
        ('claim', 'CLAIM'),
    ]
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    username = models.CharField(max_length=255, null=True, blank=True)
    user_role = models.CharField(max_length=50, null=True, blank=True)
    object_id = models.CharField(max_length=100, blank=True, null=True)
    object_repr = models.CharField(max_length=255, blank=True, null=True)
    model_name = models.CharField(max_length=100)
    old_values = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    new_values = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']
        default_permissions = ('view',) # Only allow viewing by default
        indexes = [
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]
    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M:%S} - {self.username or 'system'} - {self.action} - {self.model_name}({self.object_id})"

    def save(self, *arg, **kwargs):
        if not self._state.adding:
            raise PermissionDenied("Direct updates to AuditLog entries are not allowed.")
        super().save(*arg, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Direct deletions of AuditLog entries are not allowed.")