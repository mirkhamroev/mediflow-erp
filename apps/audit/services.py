from apps.commons.middleware import get_client_ip, get_current_request
from .models import AuditLog
from django.forms.models import model_to_dict

SENSITIVE_FIELDS = {'password', 'token', 'otp', 'code'}


def _clean(values):
    if not values:
        return values
    return {k: ('***' if k in SENSITIVE_FIELDS else v) for k, v in values.items()}

def snapshot_instance(instance):
    """
    Create a snapshot of the instance's current state.
    """
    if instance is None:
        return None
    return _clean(model_to_dict(instance))

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
        model_name = model_name or instance.__class__.__name__
        object_id = object_id or str(instance.pk)

    return AuditLog.objects.create(
        action=action,
        user=user,
        username=getattr(user, 'username', None) if user else None,
        user_role=getattr(user, 'role', None) if user else None,
        model_name=model_name,
        object_id=object_id,
        object_repr=str(instance) if instance else '',
        old_values=_clean(old_values),
        new_values=_clean(new_values),
        ip_address=get_client_ip(request) if request else None,
        user_agent=request.META.get('HTTP_USER_AGENT') if request else ''
    )