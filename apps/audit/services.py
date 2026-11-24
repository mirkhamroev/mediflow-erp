from apps.commons.middleware import get_client_ip, get_current_request
from .models import AuditLog
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.fields.files import FieldFile

SENSITIVE_FIELDS = {'password', 'token', 'otp', 'code'}


def _clean(values):
    if not values:
        return values
    return {k: ('***' if k in SENSITIVE_FIELDS else v) for k, v in values.items()}

def snapshot_instance(instance, exclude=()):
    """
    Create a JSON-safe snapshot of the instance's current state: {field attname: value}.

    Unlike model_to_dict, it includes non-editable fields (id, created_at), stores foreign
    keys as their raw id ("hospital_id"), and turns file/image fields into their stored path,
    since FieldFile objects cannot be JSON-encoded. The JSON round-trip normalises values
    (Decimal/UUID/date -> str) so old and new snapshots compare equal when nothing changed.

    Sensitive fields are not masked here because the signals diff the raw values first;
    log_action masks them before anything is stored.
    """
    if instance is None:
        return None
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in exclude or field.attname in exclude:
            continue
        value = getattr(instance, field.attname)
        if isinstance(value, FieldFile):
            value = value.name or None
        data[field.attname] = value
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))

def log_action(*, action, instance=None, model_name='', object_id='',
               old_values=None, new_values=None, user=None, request=None):
    """
    Log an action in the audit log.
    """
    request = request or get_current_request()
    if user is None and request is not None:
        req_user = getattr(request, 'user', None)
        if req_user and req_user.is_authenticated:
            user = req_user

    if instance is not None:
        # "app_label.ModelName" (e.g. "clinical.Prescription"), unique across apps
        model_name = model_name or instance._meta.label
        object_id = object_id or str(instance.pk)

    return AuditLog.objects.create(
        action=action,
        user=user,
        # get_username() returns USERNAME_FIELD (email here); User.username is None in this project
        username=user.get_username() if user else None,
        user_role=getattr(user, 'role', None) if user else None,
        model_name=model_name,
        object_id=object_id,
        # Truncated to the column size: PostgreSQL rejects longer values instead of cutting them
        object_repr=str(instance)[:255] if instance is not None else '',
        old_values=_clean(old_values),
        new_values=_clean(new_values),
        ip_address=get_client_ip(request) if request else None,
        user_agent=request.META.get('HTTP_USER_AGENT') if request else ''
    )