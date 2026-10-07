from django.contrib import admin
from .models import User, EmailVerificationOTP, PendingRegistration

# Register your models here.

admin.site.register(User)
admin.site.register(EmailVerificationOTP)


@admin.register(PendingRegistration)
class PendingRegistrationAdmin(admin.ModelAdmin):
    """Unconfirmed sign-ups; the password and code hashes are never shown."""
    list_display = ('email', 'phone_number', 'full_name', 'created_at', 'expires_at', 'attempts')
    search_fields = ('email', 'phone_number', 'full_name')
    exclude = ('password', 'hashed_code')
