from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_delete, post_save, pre_save

from apps.commons.mixins import AuditableModelMixin
from .services import log_action, snapshot_instance


def _is_audited(sender):
    """
    True when the model class opted into auditing via AuditableModelMixin.
    Handlers are connected globally, so this filter keeps every other model untouched.
    """
    return isinstance(sender, type) and issubclass(sender, AuditableModelMixin)


def _snapshot(instance):
    """
    Snapshot of the instance's fields minus the model's audit_exclude_fields.
    Never None, so callers can diff the result directly.
    """
    return snapshot_instance(instance, exclude=instance.audit_exclude_fields) or {}


def capture_old_values(sender, instance, raw=False, **kwargs):
    """
    pre_save: load the row as it is currently stored in the database, before the save
    overwrites it, and keep its snapshot on the instance for the post_save handler.

    Skipped for new objects (nothing stored yet) and for fixture loading (raw=True),
    where the database may not be in a consistent state.
    """
    if raw or not _is_audited(sender) or instance._state.adding:
        return
    # _base_manager ignores custom default managers that could filter the row out (e.g. soft delete)
    old_instance = sender._base_manager.filter(pk=instance.pk).first()
    instance._audit_old_values = _snapshot(old_instance) if old_instance else None


def log_create_or_update(sender, instance, created, raw=False, **kwargs):
    """
    post_save: write a CREATE entry with the full new state, or an UPDATE entry holding
    only the fields that actually changed (old value -> new value).

    A save that changed nothing (e.g. save() called twice) produces no entry, so the
    log stays readable.
    """
    if raw or not _is_audited(sender):
        return

    new_values = _snapshot(instance)
    if created:
        log_action(action='create', instance=instance, new_values=new_values)
        return

    old_values = instance._audit_old_values or {}
    instance._audit_old_values = None  # don't let a later save on this instance reuse it
    changed = [field for field, value in new_values.items() if old_values.get(field) != value]
    if not changed:
        return
    log_action(
        action='update',
        instance=instance,
        old_values={field: old_values.get(field) for field in changed},
        new_values={field: new_values[field] for field in changed},
    )


def log_delete(sender, instance, **kwargs):
    """
    post_delete: write a DELETE entry with the full last state of the object, so a
    deleted record can still be reconstructed from the audit log.

    Also fires for objects removed by on_delete=CASCADE, so cascaded deletions of
    audited models are recorded too.
    """
    if not _is_audited(sender):
        return
    log_action(action='delete', instance=instance, old_values=_snapshot(instance))


def log_user_login(sender, request, user, **kwargs):
    """
    user_logged_in: write a LOGIN entry for session-based logins (e.g. Django Admin).
    """
    log_action(action='login', instance=user, user=user, request=request)


def log_user_logout(sender, request, user, **kwargs):
    """
    user_logged_out: write a LOGOUT entry for session-based logouts.
    """
    if user is not None:
        log_action(action='logout', instance=user, user=user, request=request)


def connect_signals():
    """
    Connect the handlers for all models; called once from AuditConfig.ready().
    dispatch_uid prevents duplicate connections (and duplicate log entries) if ready()
    runs more than once.
    """
    pre_save.connect(capture_old_values, dispatch_uid='audit_capture_old_values')
    post_save.connect(log_create_or_update, dispatch_uid='audit_log_create_or_update')
    post_delete.connect(log_delete, dispatch_uid='audit_log_delete')
    user_logged_in.connect(log_user_login, dispatch_uid='audit_log_user_login')
    user_logged_out.connect(log_user_logout, dispatch_uid='audit_log_user_logout')

