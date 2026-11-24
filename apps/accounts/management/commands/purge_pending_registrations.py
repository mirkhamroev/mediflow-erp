from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import PendingRegistration


class Command(BaseCommand):
    help = "Delete unconfirmed sign-ups older than PENDING_REGISTRATION_TTL_HOURS."

    def handle(self, *args, **options):
        """
        Remove PendingRegistration rows nobody verified in time, so unconfirmed personal
        data (name, phone, password hash) is not kept indefinitely. Schedule it, e.g. hourly:
            0 * * * * python manage.py purge_pending_registrations
        """
        cutoff = timezone.now() - timedelta(hours=settings.PENDING_REGISTRATION_TTL_HOURS)
        deleted, _ = PendingRegistration.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired pending registration(s)."))
