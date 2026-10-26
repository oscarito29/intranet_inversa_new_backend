from rest_framework.permissions import BasePermission

from apps.usuarios.models import Usuario


def usuario_puede_ver_financiera(usuario: Usuario, financiera_id: str) -> bool:
    """
    Control de acceso real (server-side) a documentos de una financiera.
    En el legacy esto SOLO se validaba en JavaScript — aquí se aplica siempre,
    sin importar lo que pida el cliente.
    """
    if usuario.rol_id == 1:
        return True
    return str(usuario.financiera_id) == str(financiera_id)


class EsAdministrador(BasePermission):
    """Solo rol_id == 1 (Admin) puede aprobar/rechazar/revocar documentos o fijar el rango de fechas."""

    message = 'Solo un administrador puede realizar esta acción.'

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.rol_id == 1)
