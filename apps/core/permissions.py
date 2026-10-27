from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

ROL_ADMIN = 1


class EsAdministrador(BasePermission):
    """Solo rol_id == 1 (Admin)."""

    message = 'Solo un administrador puede realizar esta acción.'

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.rol_id == ROL_ADMIN)


class AdminParaEscritura(BasePermission):
    """Cualquier usuario autenticado lee; solo un administrador crea, edita o elimina."""

    message = 'Solo un administrador puede realizar esta acción.'

    def has_permission(self, request: Request, view: APIView) -> bool:
        usuario = request.user
        if not (usuario and usuario.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return usuario.rol_id == ROL_ADMIN
