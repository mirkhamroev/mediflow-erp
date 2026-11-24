from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.audit'
    label = 'audit'

    def ready(self):
        """
        Register the audit signal handlers once the app registry is fully loaded.
        """
        from .signals import connect_signals
        connect_signals()
