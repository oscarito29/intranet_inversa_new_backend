from urllib.parse import unquote, urlparse

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction


def borrar_archivo_local(ruta: str | None) -> None:
    """
    Borra el archivo físico de una URL guardada en la base, pero SOLO si vive bajo
    MEDIA_URL (storage local). Las URLs absolutas (p. ej. el S3 del sistema anterior)
    nunca se tocan. Se ejecuta al confirmar la transacción.
    """
    if not ruta or ruta.startswith(('http://', 'https://')):
        return
    camino = unquote(urlparse(ruta).path)
    if not camino.startswith(settings.MEDIA_URL):
        return
    nombre = camino[len(settings.MEDIA_URL):]
    if not nombre or '..' in nombre.split('/'):
        return
    transaction.on_commit(lambda: default_storage.delete(nombre))


def archivo_local_disponible(url: str) -> bool:
    """
    Si el archivo de una URL guardada en la base existe de verdad. Solo se puede comprobar el storage local
    (bajo MEDIA_URL); las URLs absolutas (S3) se dan por disponibles porque no se consulta la nube por cada fila.
    """
    if url.startswith(('http://', 'https://')):
        return True
    camino = unquote(urlparse(url).path)
    if not camino.startswith(settings.MEDIA_URL):
        return True
    nombre = camino[len(settings.MEDIA_URL):]
    if not nombre or '..' in nombre.split('/'):
        return False
    return default_storage.exists(nombre)
