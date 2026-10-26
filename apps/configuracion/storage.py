import re
import uuid

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile

EXTENSIONES_PERMITIDAS = {'.jpg', '.jpeg', '.png', '.webp'}
TAMANIO_MAXIMO_BYTES = 5 * 1024 * 1024


def _sanitizar_nombre(nombre: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', nombre)


def _validar_imagen(archivo: UploadedFile) -> None:
    nombre = archivo.name or ''
    extension = ('.' + nombre.rsplit('.', 1)[-1].lower()) if '.' in nombre else ''
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ValidationError(f'Tipo de imagen no permitido ({extension or "sin extensión"}).')
    if archivo.size > TAMANIO_MAXIMO_BYTES:
        raise ValidationError('La imagen supera el tamaño máximo permitido (5MB).')


def guardar_imagen_carrusel(archivo: UploadedFile) -> str:
    _validar_imagen(archivo)
    key = f'imagenes-carrusel/{uuid.uuid4().hex}_{_sanitizar_nombre(archivo.name)}'
    ruta_guardada = default_storage.save(key, archivo)
    return default_storage.url(ruta_guardada)


def guardar_imagen_comunicado(archivo: UploadedFile) -> str:
    _validar_imagen(archivo)
    key = f'comunicados/{uuid.uuid4().hex}_{_sanitizar_nombre(archivo.name)}'
    ruta_guardada = default_storage.save(key, archivo)
    return default_storage.url(ruta_guardada)
