from rest_framework.permissions import BasePermission


class RolePermission(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in self.allowed_roles
        )


class IsAdminRole(RolePermission):
    allowed_roles = ("ADMIN",)


class IsTransporterRole(RolePermission):
    allowed_roles = ("TRANSPORTER",)


class IsDriverRole(RolePermission):
    allowed_roles = ("DRIVER",)


class IsAdminOrTransporterRole(RolePermission):
    allowed_roles = ("ADMIN", "TRANSPORTER")
