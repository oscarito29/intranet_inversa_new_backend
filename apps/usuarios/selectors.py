from datetime import datetime

from apps.financial.models import Bitacora

from .models import Usuario

DESCRIPCION_CAMBIO_PASSWORD = 'Cambio de Password del Usuario'


def ultimo_cambio_de_password(usuario: Usuario) -> datetime | None:
    """
    La tabla `user` no guarda cuándo cambió la contraseña (`updated_at` cambia con cualquier edición del perfil),
    pero cada cambio queda en la bitácora con esta descripción.
    """
    registro = (
        Bitacora.objects.filter(usuario=usuario.email, descripcion__startswith=DESCRIPCION_CAMBIO_PASSWORD).order_by('-fecha').first()
    )
    return registro.fecha if registro else None
