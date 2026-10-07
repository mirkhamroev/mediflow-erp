from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Read-only admin for the audit trail: entries can be searched and inspected,
    but never added, edited or deleted from here, not even by superusers.
    """
    list_display = ('timestamp', 'action', 'username', 'user_role', 'model_name', 'object_id', 'ip_address')
    list_filter = ('action', 'model_name', 'user_role')
    search_fields = ('username', 'object_id', 'object_repr', 'ip_address')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    # Every field is shown read-only on the detail page
    readonly_fields = [field.name for field in AuditLog._meta.fields]
    # Avoid an extra query per row for the user FK shown on the detail page
    list_select_related = ('user',)

    def has_add_permission(self, request):
        """
        Entries are only created by the audit service/signals, never by hand.
        """
        return False

    def has_change_permission(self, request, obj=None):
        """
        Audit entries are immutable; the detail page is view-only.
        """
        return False

    def has_delete_permission(self, request, obj=None):
        """
        Audit entries can never be deleted; this also removes the bulk "delete selected" action.
        """
        return False
