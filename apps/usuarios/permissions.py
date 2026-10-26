from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class EsAdministrador(BasePermission):
    """Solo usuarios con rol_id == 1 (Admin) pueden pasar."""

    message = 'Solo un administrador puede realizar esta acción.'

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.rol_id == 1)
