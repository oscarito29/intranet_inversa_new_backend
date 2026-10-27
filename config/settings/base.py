"""Configuración compartida por todos los entornos (development/production)."""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('DJANGO_SECRET_KEY', default='django-insecure-change-me-in-env')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOCAL_APPS = [
    'apps.usuarios',
    'apps.financial',
    'apps.documentos',
    'apps.configuracion',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    *LOCAL_APPS,
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# La vista previa de un PDF lo muestra dentro de la página (iframe del mismo origen, vía el proxy del frontend).
# Con el valor por defecto (DENY) el navegador lo bloquearía; SAMEORIGIN sigue impidiendo que otros sitios lo enmarquen.
X_FRAME_OPTIONS = 'SAMEORIGIN'

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

AUTH_USER_MODEL = 'usuarios.Usuario'

# El hasher legado (MD5 sin salt) solo sirve para VERIFICAR contraseñas existentes del
# sistema PHP; Argon2 es el hasher activo. Un login exitoso con el hash legado hace que
# Django re-hashee automáticamente la contraseña a Argon2 (comportamiento nativo de
# django.contrib.auth.base_user.AbstractBaseUser.check_password).
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'apps.usuarios.hashers.LegacyUnsaltedMD5PasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Tegucigalpa'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

# Almacenamiento local de documentos subidos (dev). El bucket S3 real de
# producción NO se usa aquí — ver apps/financial/storage.py.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Permite subir documentos de hasta ~15MB sin que Django los rechace antes de
# llegar a la validación explícita de tamaño en apps/financial/services.py.
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'config.exception_handler.custom_exception_handler',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    # Cada refresh emite un token nuevo y deja el anterior en la lista negra; el logout también.
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    # La tabla `user` legacy no tiene columna `last_login` (viene de
    # AbstractBaseUser); si esto quedara en True, SimpleJWT intentaría
    # escribirla en cada login y fallaría con "Unknown column".
    'UPDATE_LAST_LOGIN': False,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Intranet Inversa API',
    'DESCRIPTION': 'API de la Intranet Inversa (migración desde CodeIgniter 3 a Django).',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

API_BASE_PATH = 'api/v1'

REFRESH_TOKEN_COOKIE_NAME = 'refresh_token'
REFRESH_TOKEN_COOKIE_SECURE = True
REFRESH_TOKEN_COOKIE_SAMESITE = 'Lax'

# Caché de datos globales (ver apps/core/cache.py). Producción usa Redis.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'intranet-inversa',
    }
}
