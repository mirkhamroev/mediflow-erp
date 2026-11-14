from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsOwner(BasePermission):
    message = "You do not have the permission to access owner attributes."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(obj, 'user_id', None) == request.user.id:
            return True
        return getattr(obj, 'created_by_id', None) == request.user.id


class IsStaff(BasePermission):
    message = "You are not staff member, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.is_staff
        )


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and (request.user.is_staff or getattr(request.user, 'is_admin', False))
        )


# -------------- Role-Based Access Control (Phase 2.2 & 2.6) -----------------


def _has_role(request, *roles):
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated and user.is_active):
        return False
    if hasattr(user, 'has_role'):
        return user.has_role(*roles)
    return user.role in roles


class IsSuperAdmin(BasePermission):
    message = "You are not a super administrator, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated and user.is_active):
            return False
        return user.is_superuser or _has_role(request, "super_admin")


class IsHospitalAdmin(BasePermission):
    message = "You are not admin, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated and user.is_active):
            return False
        return user.is_superuser or _has_role(request, "admin", "super_admin")


class IsDoctor(BasePermission):
    message = "You are not doctor, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        return _has_role(request, "doctor")


class IsNurse(BasePermission):
    message = "You are not a nurse, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        return _has_role(request, "nurse")


class IsReceptionist(BasePermission):
    message = "You are not a receptionist, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        return _has_role(request, "receptionist")


class IsPharmacist(BasePermission):
    message = "You are not pharmacist, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        return _has_role(request, "pharmacist")


class IsAccountant(BasePermission):
    message = "You are not accountant, so you do not have permission to access to this resource."

    def has_permission(self, request, view):
        return _has_role(request, "accountant")


class IsInsuranceManager(BasePermission):
    message = "You are not an insurance manager, so you do not have permission to access this resource."

    def has_permission(self, request, view):
        return _has_role(request, "insurance_manager")


class IsClinicalStaff(BasePermission):
    """Doctors and nurses."""
    message = "Only clinical staff (doctors or nurses) can access this resource."

    def has_permission(self, request, view):
        return _has_role(request, "doctor", "nurse")


class RoleBasedPermission(BasePermission):
    """
    Factory/instance permission class for arbitrary role combinations.
    Can be used via `RoleBasedPermission.for_roles('doctor', 'nurse')` in `permission_classes`
    or instantiated directly in `get_permissions()`.
    """
    def __init__(self, *roles):
        if roles:
            self.roles = roles

    roles = ()

    @classmethod
    def for_roles(cls, *roles):
        return type(f"RoleBasedPermission_{'_'.join(roles)}", (cls,), {"roles": roles})

    def has_permission(self, request, view):
        return _has_role(request, *self.roles)


class HasRBACPermission(BasePermission):
    """
    Checks fine-grained RBAC permission codes (Phase 2.2), e.g. 'clinical.create_prescription'.
    Usage:
      - Set `required_permission = 'inventory.dispense'` (or a dict mapping action -> code) on the View/ViewSet, OR
      - Use `HasRBACPermission.with_perm('inventory.dispense')` in `permission_classes`.
    """
    message = "You do not have the required permission to perform this action."
    perm_codes = ()

    def __init__(self, *perm_codes):
        if perm_codes:
            self.perm_codes = perm_codes

    @classmethod
    def with_perm(cls, *perm_codes):
        return type(f"HasRBACPermission_{'_'.join(perm_codes)}", (cls,), {"perm_codes": perm_codes})

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated and user.is_active):
            return False

        codes = self.perm_codes
        if not codes:
            view_perms = getattr(view, 'required_permission', None)
            if isinstance(view_perms, dict):
                action = getattr(view, 'action', request.method.lower())
                action_perm = view_perms.get(action)
                if action_perm is None:
                    return True
                codes = (action_perm,) if isinstance(action_perm, str) else tuple(action_perm)
            elif isinstance(view_perms, str):
                codes = (view_perms,)
            elif view_perms:
                codes = tuple(view_perms)

        if not codes:
            return True
        return user.has_rbac_perm(*codes)


def _extract_organization_id(obj):
    if hasattr(obj, 'organization_id') and obj.organization_id:
        return obj.organization_id
    if hasattr(obj, 'hospital') and obj.hospital is not None:
        return obj.hospital.organization_id
    if hasattr(obj, 'staff_profile') and obj.staff_profile is not None:
        return obj.staff_profile.organization_id
    if obj.__class__.__name__ == 'Organization':
        return obj.pk
    return None


def _extract_hospital_id(obj):
    if hasattr(obj, 'hospital_id') and obj.hospital_id:
        return obj.hospital_id
    if hasattr(obj, 'staff_profile') and obj.staff_profile is not None:
        return obj.staff_profile.hospital_id
    if obj.__class__.__name__ == 'Hospital':
        return obj.pk
    return None


class IsSameOrganization(BasePermission):
    """
    Object-level permission ensuring the acting staff member belongs to the same
    Organization as the target object. Superusers and super_admins bypass this check.
    """
    message = "You do not have permission to access records outside your organization."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or _has_role(request, "super_admin"):
            return True
        staff = getattr(user, 'staff_profile', None)
        if not staff or not staff.is_active:
            return False
        target_org_id = _extract_organization_id(obj)
        return target_org_id is not None and staff.organization_id == target_org_id


class IsSameHospital(BasePermission):
    """
    Object-level permission ensuring the acting staff member belongs to the same
    Hospital as the target object. Superusers, super_admins, and hospital admins of the
    same organization are permitted.
    """
    message = "You do not have permission to access records outside your hospital."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or _has_role(request, "super_admin"):
            return True
        staff = getattr(user, 'staff_profile', None)
        if not staff or not staff.is_active:
            return False
        target_hospital_id = _extract_hospital_id(obj)
        return target_hospital_id is not None and staff.hospital_id == target_hospital_id


class CanViewAuditLog(BasePermission):
    """
    Audit log access: hospital admins (role "admin" or "super_admin"), superusers,
    or any user explicitly granted the audit.view_auditlog / 'audit.read' permission.
    """
    message = "You do not have permission to view the audit log."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        return (
            _has_role(request, "admin", "super_admin")
            or user.has_perm('audit.view_auditlog')
            or (hasattr(user, 'has_rbac_perm') and user.has_rbac_perm('audit.read'))
        )

