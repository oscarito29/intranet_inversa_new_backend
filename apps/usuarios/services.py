import re
import uuid

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from apps.financial.models import Bitacora

from .models import Usuario

EXTENSIONES_FOTO = {'.jpg', '.jpeg', '.png', '.webp'}
TAMANIO_MAXIMO_FOTO_BYTES = 2 * 1024 * 1024
ROL_USUARIO = 2


def _registrar_bitacora(usuario: Usuario, descripcion: str) -> None:
    Bitacora.objects.create(usuario=usuario.email, accion='Edicion', descripcion=descripcion[:100], fecha=timezone.now())


def actualizar_perfil(usuario: Usuario, name: str, phone_number: str, email: str | None) -> Usuario:
    """El rol Usuario no puede cambiar su correo (igual que el legacy); solo un admin."""
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
    return usuario


def cambiar_password(usuario: Usuario, actual: str, nuevo: str) -> None:
    if not usuario.check_password(actual):
        raise ValidationError({'actual': 'La contraseña actual es incorrecta.'})

    usuario.set_password(nuevo)
    usuario.updated_at = timezone.now()
    usuario.save(update_fields=['password', 'updated_at'])
    _registrar_bitacora(usuario, f'Cambio de Password del Usuario {usuario.email}')


def guardar_foto_perfil(usuario: Usuario, archivo: UploadedFile) -> Usuario:
    nombre = archivo.name or ''
    extension = ('.' + nombre.rsplit('.', 1)[-1].lower()) if '.' in nombre else ''
    if extension not in EXTENSIONES_FOTO:
        raise ValidationError({'picture': f'Tipo de imagen no permitido ({extension or "sin extensión"}).'})
    if archivo.size > TAMANIO_MAXIMO_FOTO_BYTES:
        raise ValidationError({'picture': 'La imagen supera el tamaño máximo permitido (2MB).'})

    nombre_seguro = re.sub(r'[^A-Za-z0-9._-]+', '_', nombre)
    ruta_guardada = default_storage.save(f'perfiles/{usuario.id}_{uuid.uuid4().hex[:8]}_{nombre_seguro}', archivo)

    usuario.picture = default_storage.url(ruta_guardada)
    usuario.updated_at = timezone.now()
    usuario.save(update_fields=['picture', 'updated_at'])
    return usuario
