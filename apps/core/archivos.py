from urllib.parse import unquote, urlparse

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import File
from django.db import transaction

# Lo que se guarda en la base para un archivo subido con este sistema: `storage:<clave>`. La clave es estable; la
# dirección para abrirlo NO se guarda, se calcula al responder. Con un bucket privado de S3 esa dirección está firmada
# y vence en minutos u horas, así que guardarla en la base la dejaría rota. En disco local la dirección es `/media/<clave>`.
PREFIJO_STORAGE = 'storage:'


def guardar_archivo(clave: str, archivo: File) -> str:
    """Guarda el archivo en el storage por defecto (disco en desarrollo, S3 en producción) y devuelve el valor para la base."""
    return PREFIJO_STORAGE + default_storage.save(clave, archivo)


def url_de_valor(valor: str | None) -> str | None:
    """
    La dirección para abrir lo que hay en la base. Un valor `storage:<clave>` se resuelve con el storage actual
    (en S3, una dirección firmada y temporal); cualquier otro (la URL absoluta del bucket del sistema anterior,
    una ruta `/media/...` de antes) ya es una dirección y se entrega tal cual.
    """
    if valor and valor.startswith(PREFIJO_STORAGE):
        return default_storage.url(valor[len(PREFIJO_STORAGE):])
    return valor


def _clave_en_storage(valor: str | None) -> str | None:
    if valor and valor.startswith(PREFIJO_STORAGE):
        clave = valor[len(PREFIJO_STORAGE):]
        return clave if clave and '..' not in clave.split('/') else None
    return None


def borrar_archivo(valor: str | None) -> None:
    """
    Borra el archivo de un valor guardado en la base, pero solo si lo subió este sistema (`storage:<clave>`) o es una
    ruta bajo MEDIA_URL de antes. Las URLs absolutas (el S3 del sistema anterior) nunca se tocan. Se ejecuta al
    confirmar la transacción, para no borrar un archivo si la escritura se revierte.
    """
    clave = _clave_en_storage(valor)
    if clave is not None:
        transaction.on_commit(lambda: default_storage.delete(clave))
        return
    borrar_archivo_local(valor)


def borrar_archivo_local(ruta: str | None) -> None:
    """Borra un archivo guardado como ruta bajo MEDIA_URL (el formato anterior a `storage:`)."""
    if not ruta or ruta.startswith(('http://', 'https://')):
        return
    camino = unquote(urlparse(ruta).path)
    if not camino.startswith(settings.MEDIA_URL):
        return
    nombre = camino[len(settings.MEDIA_URL):]
    if not nombre or '..' in nombre.split('/'):
        return
    transaction.on_commit(lambda: default_storage.delete(nombre))


def archivo_local_disponible(url: str | None) -> bool:
    """
    Si el archivo de una URL guardada en la base existe de verdad. Solo se puede comprobar el storage local
    (bajo MEDIA_URL); las URLs absolutas (S3) se dan por disponibles porque no se consulta la nube por cada fila.
    """
    if not url:
        return False
    if url.startswith(('http://', 'https://')):
        return True
    if url.startswith(PREFIJO_STORAGE):
        return default_storage.exists(url[len(PREFIJO_STORAGE):])
    camino = unquote(urlparse(url).path)
    if not camino.startswith(settings.MEDIA_URL):
        return True
    nombre = camino[len(settings.MEDIA_URL):]
    if not nombre or '..' in nombre.split('/'):
        return False
    return default_storage.exists(nombre)
