"""
Validación de archivos subidos por su contenido, no solo por el nombre.

La extensión y el `Content-Type` los escribe quien sube el archivo: un ejecutable o una página con scripts puede
llamarse `balance.pdf`. Aquí se lee el principio del archivo (su «firma») y se comprueba que sea del formato que dice
la extensión. Lo que no se puede comprobar con una firma (texto plano) se revisa de otra forma.
"""

import mimetypes
import zipfile
from pathlib import PurePath

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

BYTES_A_LEER = 8192

# extensión → (formato, tipo MIME que se guarda). El MIME sale de aquí y no del encabezado que manda el navegador.
FORMATOS = {
    '.pdf': ('pdf', 'application/pdf'),
    '.png': ('png', 'image/png'),
    '.jpg': ('jpg', 'image/jpeg'),
    '.jpeg': ('jpg', 'image/jpeg'),
    '.webp': ('webp', 'image/webp'),
    '.docx': ('docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    '.xlsx': ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    '.doc': ('ole', 'application/msword'),
    '.xls': ('ole', 'application/vnd.ms-excel'),
    '.rar': ('rar', 'application/vnd.rar'),
    '.txt': ('txt', 'text/plain'),
}

_FIRMAS = {
    'pdf': (b'%PDF-',),
    'png': (b'\x89PNG\r\n\x1a\n',),
    'jpg': (b'\xff\xd8\xff',),
    'ole': (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1',),
    'rar': (b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00'),
}
# Un .docx o .xlsx es un zip con una carpeta propia de cada programa.
_CARPETA_OOXML = {'docx': 'word/', 'xlsx': 'xl/'}


def extension_de(nombre: str | None) -> str:
    return PurePath(nombre or '').suffix.lower()


def tipo_mime_de(nombre: str | None) -> str:
    """El tipo MIME según la extensión (ya validada); sin extensión conocida, el genérico."""
    formato = FORMATOS.get(extension_de(nombre))
    return formato[1] if formato else (mimetypes.guess_type(nombre or '')[0] or 'application/octet-stream')


def _coincide_con_la_firma(formato: str, inicio: bytes, archivo: UploadedFile) -> bool:
    if formato == 'webp':
        return inicio[:4] == b'RIFF' and inicio[8:12] == b'WEBP'
    if formato in _CARPETA_OOXML:
        archivo.seek(0)
        try:
            with zipfile.ZipFile(archivo) as comprimido:
                nombres = comprimido.namelist()
        except zipfile.BadZipFile:
            return False
        finally:
            archivo.seek(0)
        return '[Content_Types].xml' in nombres and any(nombre.startswith(_CARPETA_OOXML[formato]) for nombre in nombres)
    if formato == 'txt':
        # Texto plano no tiene firma, pero sí una señal clara de que NO lo es: los bytes nulos de un binario.
        return b'\x00' not in inicio
    return any(inicio.startswith(firma) for firma in _FIRMAS[formato])


def validar_contenido(archivo: UploadedFile) -> None:
    """Falla si el archivo está vacío o si su contenido no es del formato que anuncia su extensión."""
    extension = extension_de(archivo.name)
    formato = FORMATOS.get(extension)
    if formato is None:
        raise ValidationError(f'Tipo de archivo no permitido ({extension or "sin extensión"}).')
    if archivo.size == 0:
        raise ValidationError('El archivo está vacío.')

    archivo.seek(0)
    inicio = archivo.read(BYTES_A_LEER)
    archivo.seek(0)
    if not _coincide_con_la_firma(formato[0], inicio, archivo):
        raise ValidationError(f'El contenido del archivo no corresponde a su extensión ({extension}).')
