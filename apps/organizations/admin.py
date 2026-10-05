from django.contrib import admin
from .models import Organization, Hospital, Department

# Register your models here.

admin.site.register(Organization)
admin.site.register(Hospital)
admin.site.register(Department)