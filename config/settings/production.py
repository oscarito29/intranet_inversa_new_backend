from .base import *  # noqa: F403
from .almacenamiento import opciones_s3, storages_con_s3
from .validaciones import exigir_clave_secreta

DEBUG = False

# Sin valor por defecto a propósito: con la clave de ejemplo cualquiera podría fabricar tokens de sesión válidos.
# Si falta la variable de entorno, el servidor no arranca.
SECRET_KEY = exigir_clave_secreta(env('DJANGO_SECRET_KEY'))  # noqa: F405

# Archivos subidos: con AWS_STORAGE_BUCKET_NAME van a un bucket privado de S3; sin él, al disco (solo para probar).
_opciones_s3 = opciones_s3(env)  # noqa: F405
if _opciones_s3:
    STORAGES = storages_con_s3(_opciones_s3)

API_DOCS_ENABLED = env.bool('API_DOCS_ENABLED', default=False)  # noqa: F405
ADMIN_ENABLED = env.bool('ADMIN_ENABLED', default=False)  # noqa: F405

ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=[])  # noqa: F405

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env('DB_NAME'),  # noqa: F405
        'USER': env('DB_USER'),  # noqa: F405
        'PASSWORD': env('DB_PASSWORD'),  # noqa: F405
        'HOST': env('DB_HOST'),  # noqa: F405
        'PORT': env('DB_PORT', default='3306'),  # noqa: F405
        'OPTIONS': {'charset': 'utf8mb4'},
    }
}

CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])  # noqa: F405
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ['Content-Disposition']  # nombre del archivo en las exportaciones

# Detrás de un proxy o balanceador que termina el HTTPS, Django solo ve HTTP: sin esto, la redirección a HTTPS
# entraría en un ciclo y las cookies seguras no se enviarían. Se enciende solo si de verdad hay un proxy de confianza
# que pone `X-Forwarded-Proto` (y que descarta el que mande el cliente).
if env.bool('DJANGO_BEHIND_PROXY', default=False):  # noqa: F405
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),  # noqa: F405
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),  # noqa: F405
}

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL'),  # noqa: F405
        'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
        'KEY_PREFIX': 'intranet',
    }
}
