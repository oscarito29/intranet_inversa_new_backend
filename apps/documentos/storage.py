import re
import uuid

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile

EXTENSIONES_PERMITIDAS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.txt', '.rar'}
TAMANIO_MAXIMO_BYTES = 15 * 1024 * 1024


def _sanitizar_nombre(nombre: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', nombre)


def validar_archivo(archivo: UploadedFile) -> None:
    nombre = archivo.name or ''
    extension = ('.' + nombre.rsplit('.', 1)[-1].lower()) if '.' in nombre else ''
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ValidationError(f'Tipo de archivo no permitido ({extension or "sin extensión"}).')
    if archivo.size > TAMANIO_MAXIMO_BYTES:
        raise ValidationError('El archivo supera el tamaño máximo permitido (15MB).')


def tamanio_legible(bytes_size: int) -> str:
    size = float(bytes_size)
    for unidad in ('B', 'KB', 'MB', 'GB'):
        if size < 1024:
            return f'{size:.0f} {unidad}' if unidad == 'B' else f'{size:.1f} {unidad}'
        size /= 1024
    return f'{size:.1f} TB'


def guardar_documento_institucional(archivo: UploadedFile, category_id: int) -> str:
    """
    Storage local de Django (FileSystemStorage) bajo MEDIA_ROOT — nunca el
    bucket S3 real de producción. En producción esto se reemplaza por
    S3Boto3Storage vía DEFAULT_FILE_STORAGE, sin tocar este código.
    """
    validar_archivo(archivo)
    nombre_sanitizado = _sanitizar_nombre(archivo.name)
    key = f'documentos-institucionales/{category_id}/{uuid.uuid4().hex}_{nombre_sanitizado}'
    ruta_guardada = default_storage.save(key, archivo)
    return default_storage.url(ruta_guardada)
