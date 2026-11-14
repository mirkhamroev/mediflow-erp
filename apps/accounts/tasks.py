from celery import shared_task
from django.core.mail import send_mail, EmailMultiAlternatives  # CHANGE #13 (step 5)
from django.template.loader import render_to_string  # CHANGE #13 (step 5)
from django.utils import timezone
from django.conf import settings
import smtplib
from .models import User, EmailVerificationOTP
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def send_async_email(self, subject, message, recipient_email):

    """
    Sends an email asynchronously. 
    Includes basic retry logic in case the email server is temporarily down.
    """

    try:
        logger.info(f"Sending email to {recipient_email}")
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        return f"Verification email sent to {recipient_email}"
    except smtplib.SMTPException as e:
        logger.error(f"Failed to send verification email to {recipient_email}: {str(e)}. Retrying...")
        raise self.retry(exc=e)


# ===== CHANGE #13 (step 5): dedicated task that renders the verification email
# from templates instead of the old f-string body.
# Sends multipart/alternative: the plain-text part is the real body and the HTML
# part is the alternative, which is what every mail client expects (and what keeps
# text-only readers and spam filters happy).
# `send_async_email` above is left alone as the generic one-off helper. =====
@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def send_verification_email(self, recipient_email, code, full_name=""):
    """Render and send the OTP verification email (text + HTML)."""
    context = {
        "code": code,
        "full_name": full_name,
        "site_name": getattr(settings, "SITE_NAME", "MediFlow ERP"),
        "ttl_minutes": settings.OTP_TTL_MINUTES,
        "max_attempts": settings.OTP_MAX_ATTEMPTS,
    }

    try:
        logger.info(f"Sending verification email to {recipient_email}")
        message = EmailMultiAlternatives(
            subject=f"Your {context['site_name']} verification code",
            body=render_to_string("emails/verify_email.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
        )
        message.attach_alternative(
            render_to_string("emails/verify_email.html", context), "text/html"
        )
        message.send(fail_silently=False)
        return f"Verification email sent to {recipient_email}"
    except smtplib.SMTPException as e:
        logger.error(
            f"Failed to send verification email to {recipient_email}: {str(e)}. Retrying..."
        )
        raise self.retry(exc=e)
