"""
Bloqueo temporal por intentos fallidos de inicio de sesión.

El estado vive en la caché (en producción, Redis compartido por todos los procesos), no en la base: la tabla `user`
es la del sistema anterior y no tiene dónde guardarlo. Se cuenta por correo escrito, exista o no la cuenta, para que
la respuesta no revele qué correos están registrados.
"""

import hashlib
import time

from django.core.cache import cache

MAX_INTENTOS = 5
VENTANA_SEGUNDOS = 15 * 60
BLOQUEO_SEGUNDOS = 15 * 60


def _clave(correo: str, sufijo: str) -> str:
    huella = hashlib.sha256(correo.strip().lower().encode()).hexdigest()[:32]
    return f'login:{sufijo}:{huella}'


def segundos_de_bloqueo(correo: str) -> int:
    """Segundos que faltan para poder intentar de nuevo; 0 si no está bloqueado."""
    hasta = cache.get(_clave(correo, 'bloqueo'))
    return max(0, int(hasta - time.time()) + 1) if hasta else 0


def registrar_fallo(correo: str) -> int:
    """
    Cuenta un intento fallido. Al llegar a `MAX_INTENTOS` dentro de la ventana bloquea el correo y devuelve los
    segundos de bloqueo; mientras no llegue, devuelve 0.
    """
    clave = _clave(correo, 'intentos')
    cache.add(clave, 0, VENTANA_SEGUNDOS)
    try:
        intentos = cache.incr(clave)
    except ValueError:  # la clave venció entre `add` y `incr`
        cache.set(clave, 1, VENTANA_SEGUNDOS)
        intentos = 1

    if intentos < MAX_INTENTOS:
        return 0
    cache.set(_clave(correo, 'bloqueo'), time.time() + BLOQUEO_SEGUNDOS, BLOQUEO_SEGUNDOS)
    cache.delete(clave)
    return BLOQUEO_SEGUNDOS


def limpiar(correo: str) -> None:
    cache.delete_many([_clave(correo, 'intentos'), _clave(correo, 'bloqueo')])
