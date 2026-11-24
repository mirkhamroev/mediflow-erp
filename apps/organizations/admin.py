from django.contrib import admin
from .models import (
    Organization, Hospital, Department, StaffProfile, DoctorProfile, NurseProfile,
    Ward, Room, Bed, OperatingRoom,
)

# Register your models here.

admin.site.register(Organization)
admin.site.register(Hospital)
admin.site.register(Department)
admin.site.register(StaffProfile)
admin.site.register(DoctorProfile)
admin.site.register(NurseProfile)
admin.site.register(Ward)
admin.site.register(Room)
admin.site.register(Bed)
admin.site.register(OperatingRoom)