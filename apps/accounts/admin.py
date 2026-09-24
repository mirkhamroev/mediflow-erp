from django.contrib import admin
from .models import User, EmailVerificationOTP

# Register your models here.

admin.site.register(User)
admin.site.register(EmailVerificationOTP)
