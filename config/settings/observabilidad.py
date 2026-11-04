"""Registro de lo que pasa en el servidor (logs) y aviso de errores (Sentry, opcional)."""

import logging


def configuracion_de_logs(nivel: str = 'INFO') -> dict:
    """
    Todo va a la salida estándar, una línea por evento: es lo que recogen Docker y los servicios en la nube.
    No se escriben archivos de log dentro del contenedor.
    """
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'linea': {'format': '%(asctime)s %(levelname)s %(name)s %(message)s'},
        },
        'handlers': {
            'consola': {'class': 'logging.StreamHandler', 'formatter': 'linea'},
        },
        'root': {'handlers': ['consola'], 'level': nivel},
        'loggers': {
            # Un 4xx es de quien llamó, no del servidor: no ensucia el log con avisos.
            'django.request': {'handlers': ['consola'], 'level': 'ERROR', 'propagate': False},
            # Las consultas SQL llevan datos de las personas: nunca se registran, ni con LOG_LEVEL=DEBUG.
            'django.db.backends': {'handlers': ['consola'], 'level': 'WARNING', 'propagate': False},
        },
    }


def iniciar_sentry(dsn: str, entorno: str, version: str = '') -> bool:
    """
    Conecta Sentry si hay DSN; sin él no hace nada (y `sentry_sdk` ni se importa).

    Es una intranet con datos de personas y estados financieros: el aviso de error lleva el rastro y la ruta, pero
    nunca el cuerpo de la petición, las cookies ni la identidad de quien la hizo.
    """
    if not dsn:
        return False

    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=entorno,
        release=version or None,
        integrations=[DjangoIntegration(), LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)],
        send_default_pii=False,
        max_request_body_size='never',
        traces_sample_rate=0,
    )
    return True
