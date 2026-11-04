import re
import uuid

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

from apps.core.archivos import guardar_archivo
from apps.core.subidas import validar_contenido

EXTENSIONES_PERMITIDAS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.txt', '.rar'}
TAMANIO_MAXIMO_BYTES = 15 * 1024 * 1024


def _sanitizar_nombre(nombre: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', nombre)


def validar_archivo(archivo: UploadedFile) -> None:
    nombre = archivo.name or ''
    extension = ('.' + nombre.rsplit('.', 1)[-1].lower()) if '.' in nombre else ''
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ValidationError(f'Tipo de archivo no permitido ({extension or "sin extensión"}).')
    if not archivo.size or archivo.size > TAMANIO_MAXIMO_BYTES:
        raise ValidationError('El archivo supera el tamaño máximo permitido (15MB).')
    validar_contenido(archivo)


def guardar_documento(
    archivo: UploadedFile,
    corporacion_id: str,
    financiera_id: str,
    anio: int,
    mes_id: int,
) -> str:
    """
    Guarda el archivo con una key jerárquica real (a diferencia del legacy, que
    los guardaba todos planos bajo `documentos/`). En desarrollo usa el storage
    local de Django (FileSystemStorage); en producción esto se reemplaza por
    S3Boto3Storage vía DEFAULT_FILE_STORAGE, sin tocar este código.
    """
    validar_archivo(archivo)
    nombre = archivo.name or ''
    nombre_sanitizado = _sanitizar_nombre(nombre)
    key = f'documentos/{corporacion_id}/{financiera_id}/{anio}/{mes_id}/{uuid.uuid4().hex}_{nombre_sanitizado}'
    return guardar_archivo(key, archivo)
