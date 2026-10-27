import re
import uuid

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from django.utils.crypto import get_random_string

from apps.core.archivos import borrar_archivo_local
from apps.core.bitacora import registrar_bitacora
from apps.core.cache import invalidar
from apps.core.permissions import ROL_ADMIN

from .models import Usuario
from .selectors import descripcion_cambio_password

EXTENSIONES_FOTO = {'.jpg', '.jpeg', '.png', '.webp'}
TAMANIO_MAXIMO_FOTO_BYTES = 2 * 1024 * 1024
ROL_USUARIO = 2
ESTADO_ACTIVO = 'A'
# Sin caracteres que se confunden al dictarlos (0/O, 1/l/I): la contraseña temporal se entrega a una persona.
CARACTERES_PASSWORD_TEMPORAL = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
LARGO_PASSWORD_TEMPORAL = 12


@transaction.atomic
def actualizar_perfil(usuario: Usuario, name: str, phone_number: str, email: str | None) -> Usuario:
    """El rol Usuario no puede cambiar su correo (igual que el legado); solo un administrador."""
    cambia_email = email is not None and email != usuario.email
    if cambia_email:
        if usuario.rol_id == ROL_USUARIO:
            raise ValidationError({'email': 'Tu correo solo lo puede cambiar un administrador.'})
        if Usuario.objects.filter(email=email).exclude(pk=usuario.pk).exists():
            raise ValidationError({'email': 'Ya existe un usuario con ese correo.'})
        usuario.email = email

    usuario.name = name
    usuario.full_name = name
    usuario.phone_number = phone_number
    usuario.updated_at = timezone.now()
    usuario.save(update_fields=['name', 'full_name', 'phone_number', 'email', 'updated_at'])
    invalidar('cumpleanos')
    return usuario


@transaction.atomic
def cambiar_password(usuario: Usuario, actual: str, nuevo: str) -> None:
    if not usuario.check_password(actual):
        raise ValidationError({'actual': 'La contraseña actual es incorrecta.'})

    usuario.set_password(nuevo)
    usuario.updated_at = timezone.now()
    usuario.save(update_fields=['password', 'updated_at'])
    registrar_bitacora(usuario.email, 'Edicion', descripcion_cambio_password(usuario.email))


@transaction.atomic
def guardar_foto_perfil(usuario: Usuario, archivo: UploadedFile) -> Usuario:
    nombre = archivo.name or ''
    extension = ('.' + nombre.rsplit('.', 1)[-1].lower()) if '.' in nombre else ''
    if extension not in EXTENSIONES_FOTO:
        raise ValidationError({'picture': f'Tipo de imagen no permitido ({extension or "sin extensión"}).'})
    if archivo.size > TAMANIO_MAXIMO_FOTO_BYTES:
        raise ValidationError({'picture': 'La imagen supera el tamaño máximo permitido (2MB).'})

    foto_anterior = usuario.picture
    nombre_seguro = re.sub(r'[^A-Za-z0-9._-]+', '_', nombre)
    ruta_guardada = default_storage.save(f'perfiles/{usuario.id}_{uuid.uuid4().hex[:8]}_{nombre_seguro}', archivo)

    usuario.picture = default_storage.url(ruta_guardada)
    usuario.updated_at = timezone.now()
    usuario.save(update_fields=['picture', 'updated_at'])
    borrar_archivo_local(foto_anterior)
    return usuario


@transaction.atomic
def crear_usuario(actor: Usuario, serializer) -> Usuario:
    usuario = serializer.save()
    registrar_bitacora(actor.email, 'Creacion', f'Crea el usuario {usuario.email}')
    invalidar('cumpleanos')
    return usuario


@transaction.atomic
def actualizar_usuario(actor: Usuario, serializer) -> Usuario:
    """Un administrador no puede quedarse sin acceso: no desactiva su propia cuenta ni se quita el rol de administrador."""
    usuario = serializer.instance
    datos = serializer.validated_data
    if usuario.pk == actor.pk:
        if datos.get('estado', usuario.estado) != ESTADO_ACTIVO:
            raise ValidationError({'estado': 'No puedes desactivar tu propia cuenta.'})
        if usuario.rol_id == ROL_ADMIN and datos.get('rol_id', usuario.rol_id) != ROL_ADMIN:
            raise ValidationError({'rol_id': 'No puedes quitarte tu propio rol de administrador.'})

    usuario = serializer.save()
    registrar_bitacora(actor.email, 'Edicion', f'Modifica el usuario {usuario.email}')
    invalidar('cumpleanos')
    return usuario


@transaction.atomic
def restablecer_password(actor: Usuario, usuario_id: int) -> tuple[Usuario, str]:
    """
    Asigna una contraseña temporal aleatoria y la devuelve UNA vez para que el administrador se la entregue al usuario
    (todavía no hay envío por correo). Solo queda el hash en la base y, en la bitácora, que se restableció, no la clave.
    """
    usuario = Usuario.objects.select_for_update().get(pk=usuario_id)
    if usuario.pk == actor.pk:
        raise ValidationError('Para cambiar tu propia contraseña usa «Mi perfil».')

    temporal = get_random_string(LARGO_PASSWORD_TEMPORAL, CARACTERES_PASSWORD_TEMPORAL)
    usuario.set_password(temporal)
    usuario.updated_at = timezone.now()
    usuario.save(update_fields=['password', 'updated_at'])
    registrar_bitacora(actor.email, 'Edicion', descripcion_cambio_password(usuario.email))
    return usuario, temporal
