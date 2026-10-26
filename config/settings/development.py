from .base import *  # noqa: F403

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

DATABASES = {
    'default': {
        # Shim de compatibilidad por el MariaDB 10.1.38 local; ver config/db_compat/base.py.
        'ENGINE': 'config.db_compat',
        'NAME': env('DB_NAME', default='intranet_inversa'),  # noqa: F405
        'USER': env('DB_USER', default='root'),  # noqa: F405
        'PASSWORD': env('DB_PASSWORD', default=''),  # noqa: F405
        'HOST': env('DB_HOST', default='127.0.0.1'),  # noqa: F405
        'PORT': env('DB_PORT', default='3306'),  # noqa: F405
        'OPTIONS': {'charset': 'utf8mb4'},
    }
}

CORS_ALLOWED_ORIGINS = [
    'http://127.0.0.1:5173',
    'http://localhost:5173',
    'http://127.0.0.1:5174',
    'http://localhost:5174',
]
CORS_ALLOW_CREDENTIALS = True

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# En dev el frontend corre en http://127.0.0.1 (sin TLS), así que la cookie no puede ser Secure.
REFRESH_TOKEN_COOKIE_SECURE = False
