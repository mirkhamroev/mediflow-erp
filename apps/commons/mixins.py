from rest_framework.mixins import RetrieveModelMixin
from rest_framework.response import Response


class AuditableModelMixin:
    """
    Opt-in marker for models whose CREATE/UPDATE/DELETE must be written to the audit log.

    Usage:
        class Prescription(AuditableModelMixin, models.Model):
            audit_exclude_fields = ('updated_at', 'internal_note')

    The actual logging is done by the signal handlers in apps/audit/signals.py, which only
    react to subclasses of this mixin. Keeping the mixin free of audit imports means commons
    does not depend on the audit app.

    Not covered by signals (log these explicitly with apps.audit.services.log_action):
    QuerySet.update(), bulk_create(), bulk_update() and raw SQL.
    """

    # Fields left out of old/new values. updated_at changes on every save, so including it
    # would make every UPDATE entry show a change even when nothing meaningful changed.
    audit_exclude_fields = ('updated_at',)

    # Filled by the pre_save handler with the row's state before the save, read by post_save
    _audit_old_values = None


class AuditRetrieveMixin(RetrieveModelMixin):
    """
    DRF viewset mixin that logs a VIEW entry every time a single object is retrieved.

    Signals cannot see reads, so VIEW events (e.g. a doctor opening a patient record)
    have to be captured at the API layer. Use it in place of RetrieveModelMixin, or put it
    before ModelViewSet/ReadOnlyModelViewSet in the bases so its retrieve() wins.
    """

    def retrieve(self, request, *args, **kwargs):
        """
        Same as RetrieveModelMixin.retrieve, plus a VIEW audit entry for the returned object.
        Reimplemented instead of calling super() so get_object() is only queried once.
        """
        # Imported here to avoid a commons -> audit import at module load (circular import risk)
        from apps.audit.services import log_action

        instance = self.get_object()
        serializer = self.get_serializer(instance)
        log_action(action='view', instance=instance, request=request)
        return Response(serializer.data)
