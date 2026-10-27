from datetime import datetime

from django.db.models import QuerySet

from apps.financial.models import Bitacora

from .models import Usuario


def descripcion_cambio_password(email: str) -> str:
    """Texto que queda en la bitácora cuando se cambia o se restablece la contraseña de `email`."""
    return f'Cambio de Password del Usuario {email}'


def listar_usuarios() -> QuerySet[Usuario]:
    return Usuario.objects.order_by('name')


def obtener_usuario(usuario_id: int) -> Usuario:
    return Usuario.objects.get(pk=usuario_id)


def ultimo_cambio_de_password(usuario: Usuario) -> datetime | None:
    """
    La tabla `user` no guarda cuándo cambió la contraseña (`updated_at` cambia con cualquier edición del perfil),
    pero cada cambio queda en la bitácora con esta descripción, lo haya hecho el propio usuario o un administrador.
    """
    registro = Bitacora.objects.filter(descripcion=descripcion_cambio_password(usuario.email)).order_by('-fecha').first()
    return registro.fecha if registro else None
