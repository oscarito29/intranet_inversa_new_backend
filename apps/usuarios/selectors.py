from datetime import datetime

from django.db.models import Q, QuerySet

from apps.financial.models import Bitacora

from .models import Usuario


def descripcion_cambio_password(email: str) -> str:
    """Texto que queda en la bitácora cuando se cambia o se restablece la contraseña de `email`."""
    return f'Cambio de Password del Usuario {email}'


def listar_usuarios() -> QuerySet[Usuario]:
    return Usuario.objects.prefetch_related('entidades_adicionales').order_by('name')


DIRECTORIO_MAXIMO = 200


def listar_directorio(texto: str = '', financiera_id: str = '') -> dict:
    """
    Las personas activas con lo que se comparte en el directorio. `texto` busca en el nombre, el correo y la entidad.
    Trae como máximo `DIRECTORIO_MAXIMO`; `total` dice cuántas coinciden en realidad, para avisar si hay más.
    Solo esas columnas: la dirección y la fecha de nacimiento completa (con el año) no salen de aquí.
    """
    consulta = Usuario.objects.filter(estado='A', deleted_at__isnull=True).select_related('financiera__corporacion')
    if texto:
        consulta = consulta.filter(Q(name__icontains=texto) | Q(email__icontains=texto) | Q(financiera__nombre__icontains=texto))
    if financiera_id:
        consulta = consulta.filter(financiera_id=financiera_id)
    consulta = consulta.order_by('name', 'id')
    return {'total': consulta.count(), 'personas': list(consulta[:DIRECTORIO_MAXIMO])}


def obtener_usuario(usuario_id: int) -> Usuario:
    return Usuario.objects.prefetch_related('entidades_adicionales').get(pk=usuario_id)


def ultimo_cambio_de_password(usuario: Usuario) -> datetime | None:
    """
    La tabla `user` no guarda cuándo cambió la contraseña (`updated_at` cambia con cualquier edición del perfil),
    pero cada cambio queda en la bitácora con esta descripción, lo haya hecho el propio usuario o un administrador.
    """
    registro = Bitacora.objects.filter(descripcion=descripcion_cambio_password(usuario.email)).order_by('-fecha').first()
    return registro.fecha if registro else None
