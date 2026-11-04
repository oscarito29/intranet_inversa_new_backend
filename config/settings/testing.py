from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}

# Sin migraciones reales para las apps locales: las tablas salen de los modelos (ver test_runner).
MIGRATION_MODULES = {app.split('.')[-1]: None for app in LOCAL_APPS}  # noqa: F405

TEST_RUNNER = 'config.test_runner.ManagedModelTestRunner'

CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'tests'}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
REFRESH_TOKEN_COOKIE_SECURE = False

# Las pruebas inician sesión muchas veces desde la misma dirección; el límite se prueba aparte (ver test_bloqueo).
REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': {'login': '10000/min', 'password': '10000/min'}}  # noqa: F405

MEDIA_ROOT = BASE_DIR / 'media_test'  # noqa: F405
