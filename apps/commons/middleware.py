import contextvars

_request_ctx = contextvars.ContextVar('audit_request', default=None)

def get_current_request():
    """
    Get the current request from the context variable.
    """
    return _request_ctx.get()

def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')

class AuditContextMiddleware:
    """
    middleware to set the current requestin a context vairable, so that it can be accessed in the audit log service.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request_ctx.set(request)
        try:
            return self.get_response(request)
        finally:
            _request_ctx.reset(token)