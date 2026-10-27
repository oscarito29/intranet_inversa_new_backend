"""
Pasa a este sistema los archivos que el sistema anterior dejó en su propio bucket.

Cada fila de la base que apunta a una URL absoluta (la del bucket viejo) se descarga, se valida por su contenido, se
sube al storage actual y la fila queda como `storage:<clave>`. Sin `--aplicar` solo cuenta y lista lo que haría: no
descarga ni escribe nada. Se puede repetir: lo que ya se migró no vuelve a tocarse.

    python manage.py migrar_archivos_legados                      # ensayo, no cambia nada
    python manage.py migrar_archivos_legados --origen bucket.s3.amazonaws.com --aplicar

Si los archivos viejos ya están en el MISMO bucket que usa este sistema, no hace falta bajarlos y subirlos de nuevo:
con `--en-sitio NOMBRE_DEL_BUCKET` la fila pasa a apuntar a la clave que ya existe (se comprueba que el archivo esté).
Eso sí, un bucket que antes era público hay que cerrarlo DESPUÉS de correr esto: las direcciones sin firma de las filas
que aún no se migraron dejarían de abrir.
"""

import re
import urllib.request
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.configuracion.models import Comunicado, Imagen
from apps.core.archivos import PREFIJO_STORAGE, guardar_archivo
from apps.core.bitacora import registrar_bitacora
from apps.core.subidas import validar_contenido
from apps.documentos.models import Upload
from apps.financial.models import Documento
from apps.usuarios.models import Usuario

TAMANIO_MAXIMO_BYTES = 20 * 1024 * 1024
SEGUNDOS_DE_ESPERA = 30


@dataclass(frozen=True)
class Origen:
    modelo: type
    columna: str
    carpeta: str


ORIGENES = (
    Origen(Documento, 'ruta_archivo', 'legado/estados-financieros'),
    Origen(Upload, 'fname', 'legado/documentos-institucionales'),
    Origen(Imagen, 'ruta_img', 'legado/carrusel'),
    Origen(Comunicado, 'imagen', 'legado/comunicados'),
    Origen(Usuario, 'picture', 'legado/perfiles'),
)


def descargar(url: str) -> bytes:
    """Baja el archivo con un tope de tamaño, para que una URL rara no llene la memoria."""
    with urllib.request.urlopen(url, timeout=SEGUNDOS_DE_ESPERA) as respuesta:  # noqa: S310 (solo http/https, ver `es_url_a_migrar`)
        contenido = respuesta.read(TAMANIO_MAXIMO_BYTES + 1)
    if len(contenido) > TAMANIO_MAXIMO_BYTES:
        raise ValueError('el archivo supera los 20 MB')
    return contenido


def nombre_de(url: str) -> str:
    nombre = unquote(urlparse(url).path.rsplit('/', 1)[-1]) or 'archivo'
    return re.sub(r'[^A-Za-z0-9._-]+', '_', nombre)


def es_url_a_migrar(valor: str | None, hosts: list[str]) -> bool:
    if not valor or valor.startswith(PREFIJO_STORAGE) or not valor.startswith(('http://', 'https://')):
        return False
    return not hosts or urlparse(valor).hostname in hosts


def clave_en_bucket(url: str, bucket: str) -> str | None:
    """La clave de un archivo si la URL es de ese bucket de S3 (con el nombre en el host o en la ruta), si no, `None`."""
    partes = urlparse(url)
    host, ruta = partes.hostname or '', unquote(partes.path).lstrip('/')
    if host == f'{bucket}.s3.amazonaws.com' or (host.startswith(f'{bucket}.s3.') and host.endswith('.amazonaws.com')):
        return ruta or None
    if re.fullmatch(r's3(\.[a-z0-9-]+)?\.amazonaws\.com', host) and ruta.startswith(f'{bucket}/'):
        return ruta[len(bucket) + 1:] or None
    return None


class Command(BaseCommand):
    help = 'Descarga los archivos del bucket del sistema anterior y los pasa al storage actual (ensayo si no se pasa --aplicar).'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true', help='Hace los cambios. Sin esto solo muestra lo que haría.')
        parser.add_argument('--origen', action='append', default=[], metavar='HOST', help='Solo las URLs de este host (se puede repetir). Sin esto, todas las URLs absolutas.')
        parser.add_argument('--en-sitio', metavar='BUCKET', default='', help='Los archivos de este bucket no se descargan: la fila apunta a su clave actual (el bucket debe ser el que usa este sistema).')
        parser.add_argument('--limite', type=int, default=0, help='Máximo de archivos por tabla (para probar con pocos).')

    def handle(self, *args, aplicar: bool, origen: list[str], limite: int, en_sitio: str, **opciones):
        self.en_sitio = en_sitio
        totales = {'migrados': 0, 'pendientes': 0, 'fallidos': 0}

        for fuente in ORIGENES:
            filas = [
                (pk, valor)
                for pk, valor in fuente.modelo.objects.values_list('pk', fuente.columna)
                if es_url_a_migrar(valor, origen)
            ]
            if limite:
                filas = filas[:limite]
            self.stdout.write(f'{fuente.modelo._meta.db_table}.{fuente.columna}: {len(filas)} archivo(s) a migrar')

            for pk, url in filas:
                if not aplicar:
                    totales['pendientes'] += 1
                    en_sitio = ' (en sitio)' if self.en_sitio and clave_en_bucket(url, self.en_sitio) else ''
                    self.stdout.write(f'  [ensayo] {pk}: {url}{en_sitio}')
                    continue
                try:
                    self._migrar(fuente, pk, url)
                    totales['migrados'] += 1
                except (OSError, ValueError, ValidationError) as error:
                    totales['fallidos'] += 1
                    self.stderr.write(f'  [falló] {fuente.modelo._meta.db_table} {pk} ({url}): {error}')

        if aplicar:
            registrar_bitacora('sistema', 'Migracion', f'Migra {totales["migrados"]} archivos del sistema anterior ({totales["fallidos"]} fallaron)')
            self.stdout.write(self.style.SUCCESS(f'Migrados: {totales["migrados"]}. Fallidos: {totales["fallidos"]}.'))
        else:
            self.stdout.write(self.style.WARNING(f'Ensayo: {totales["pendientes"]} archivo(s) se migrarían. Agrega --aplicar para hacerlo.'))

    def _migrar(self, fuente: Origen, pk: int, url: str) -> None:
        clave = clave_en_bucket(url, self.en_sitio) if self.en_sitio else None
        if clave is not None:
            if not default_storage.exists(clave):
                raise ValueError(f'no está en el bucket: {clave}')
            fuente.modelo.objects.filter(pk=pk).update(**{fuente.columna: PREFIJO_STORAGE + clave})
            return

        nombre = nombre_de(url)
        archivo = SimpleUploadedFile(nombre, descargar(url))
        validar_contenido(archivo)  # lo que no es del formato que dice su extensión no entra al sistema nuevo
        with transaction.atomic():
            valor = guardar_archivo(f'{fuente.carpeta}/{pk}_{nombre}', archivo)
            fuente.modelo.objects.filter(pk=pk).update(**{fuente.columna: valor})
