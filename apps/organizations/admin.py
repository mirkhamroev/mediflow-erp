from django.contrib import admin
from .models import Organization, Hospital, Department, StaffProfile, DoctorProfile, NurseProfile

# Register your models here.

admin.site.register(Organization)
admin.site.register(Hospital)
admin.site.register(Department)
admin.site.register(StaffProfile)
admin.site.register(DoctorProfile)
admin.site.register(NurseProfile)