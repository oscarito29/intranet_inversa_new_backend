"""Dónde se guardan los archivos subidos: disco en desarrollo, un bucket privado de S3 en producción."""

from django.core.exceptions import ImproperlyConfigured

# Un día laboral. Las direcciones firmadas de S3 vencen; el frontend guarda las listas en caché hasta que algo las
# invalida, así que una dirección demasiado corta se rompería con la pantalla abierta (y demasiado larga, si se
# filtra, deja el documento abierto más tiempo). Se ajusta con S3_URL_EXPIRA_SEGUNDOS.
EXPIRACION_POR_DEFECTO_SEGUNDOS = 8 * 60 * 60


def opciones_s3(env) -> dict | None:
    """
    Opciones del storage de S3, o `None` si no hay bucket configurado (se queda el disco local).

    El bucket debe ser PRIVADO: los archivos se abren con direcciones firmadas y temporales, nunca públicas.
    Las credenciales son opcionales: en AWS lo normal es un rol de la máquina o del contenedor, sin claves en el entorno.
    """
    bucket = env('AWS_STORAGE_BUCKET_NAME', default='')
    if not bucket:
        return None

    opciones = {
        'bucket_name': bucket,
        'region_name': env('AWS_S3_REGION_NAME', default='us-east-1'),
        'querystring_auth': True,
        'querystring_expire': env.int('S3_URL_EXPIRA_SEGUNDOS', default=EXPIRACION_POR_DEFECTO_SEGUNDOS),
        'signature_version': 's3v4',
        'default_acl': None,
        'file_overwrite': False,
        'addressing_style': 'virtual',
    }

    clave, secreta = env('AWS_ACCESS_KEY_ID', default=''), env('AWS_SECRET_ACCESS_KEY', default='')
    if bool(clave) != bool(secreta):
        raise ImproperlyConfigured('AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY van juntas: define las dos o ninguna (para usar el rol de la máquina).')
    if clave:
        opciones.update(access_key=clave, secret_key=secreta)
    return opciones


def storages_con_s3(opciones: dict) -> dict:
    return {
        'default': {'BACKEND': 'storages.backends.s3.S3Storage', 'OPTIONS': opciones},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
