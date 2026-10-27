"""
Caché de datos GLOBALES (iguales para todos los usuarios). Nunca cachear listas que
dependan del usuario, su rol o su financiera.

Cada clave pertenece a un espacio (`espacio:resto`). `invalidar('espacio')` sube la versión
del espacio y deja huérfanas todas sus claves, sin necesitar borrado por patrón (que
LocMem no tiene). El TTL siempre está presente como red de seguridad: mientras el sistema
anterior siga escribiendo en la misma base, esas escrituras no pasan por Django.
"""

import time
from collections.abc import Callable
from typing import Any

from django.core.cache import cache
from django.db import transaction

TTL_POR_DEFECTO = 60 * 5
_PREFIJO = 'intranet'
_AUSENTE = object()


def _version(espacio: str) -> str:
    clave = f'{_PREFIJO}:version:{espacio}'
    version = cache.get(clave)
    if version is None:
        version = str(time.time_ns())
        cache.set(clave, version, None)
    return version


def _clave_completa(clave: str) -> str:
    espacio = clave.split(':', 1)[0]
    return f'{_PREFIJO}:{espacio}:{_version(espacio)}:{clave}'


def cached(clave: str, ttl: int, cargador: Callable[[], Any]) -> Any:
    completa = _clave_completa(clave)
    valor = cache.get(completa, _AUSENTE)
    if valor is _AUSENTE:
        valor = cargador()
        cache.set(completa, valor, ttl)
    return valor


def invalidar(*espacios: str) -> None:
    """Invalida al confirmar la transacción, para no borrar la caché si la escritura se revierte."""

    def _subir_version() -> None:
        for espacio in espacios:
            cache.set(f'{_PREFIJO}:version:{espacio}', str(time.time_ns()), None)

    transaction.on_commit(_subir_version)
