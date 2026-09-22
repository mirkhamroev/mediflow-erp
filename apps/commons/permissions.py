from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsOwner(BasePermission):
    message = "You do not have the permission to access owner attributes."

    def has_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        return getattr(obj, 'created_by_id', None) == request.user.id


class IsStaff(BasePermission):

    message = "You are not staff member, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )

class IsAdminOrReadOnly(BasePermission):

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )
    pass

#-------------- Role-Based Access Control     -----------------


def _has_role(request, *roles):
    return (request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.role in roles)


class IsDoctor(BasePermission):
    message = "You are not doctor, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        return _has_role(request, "doctor")

class IsHospitalAdmin(BasePermission):
    message = "You are not admin, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        return _has_role(request, "admin")

class IsPharmacist(BasePermission):
    message = "You are not pharmacist, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        return _has_role(request, "pharmacist")

class IsAccountant(BasePermission):
    message = "You are not accountant, so you do not have permission to access to this resource."

    def has_permission(self, request, view):
        return _has_role(request, "accountant")

class RoleBasedPermission(BasePermission):

    def __init__(self, *roles):
        self.roles = roles

    def has_permission(self, request, view):
        return _has_role(request, *self.roles)