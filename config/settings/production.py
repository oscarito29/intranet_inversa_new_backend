from .base import *  # noqa: F403

DEBUG = False

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
