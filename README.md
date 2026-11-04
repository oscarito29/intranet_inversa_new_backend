# Backend — Intranet Inversa

Backend de la intranet de Grupo Inversa. Migración desde una intranet legacy en CodeIgniter 3/PHP, siguiendo el patrón arquitectónico de Academic 2.0 (Django por capas: `models` / `selectors` / `services` / `views`).

## Stack

Django 5.2 · Django REST Framework · SimpleJWT · drf-spectacular · MySQL (PyMySQL) · Argon2

## Estructura

```
config/
├── settings/        # base.py / development.py / production.py
└── db_compat/       # shim de compatibilidad para MariaDB local antiguo (solo dev)
apps/
├── core/            # Transversal: permisos, bitácora, caché, archivos (S3), subidas, exportación, salud
├── usuarios/        # Auth JWT + gestión de usuarios (tabla `user` legacy)
├── financial/        # Estados financieros (piloto): catálogos, documentos, aprobación
├── documentos/        # Categorías, documentos institucionales, etiquetas
└── configuracion/     # Imágenes del carrusel, comunicados, actividades
```

Los modelos mapean tablas MySQL ya existentes (`managed = False`); no se tocan los datos reales de producción, y nunca se usa el bucket S3 ni Microsoft Graph reales — el storage y el correo usan backends locales en desarrollo (ver `docs/` de cada decisión si aplica).

## Desarrollo

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows
pip install -r requirements/development.txt
cp .env.example .env         # ajusta credenciales de BD y genera un DJANGO_SECRET_KEY propio
python manage.py migrate
python manage.py runserver 127.0.0.1:8010
```

API docs: `http://127.0.0.1:8010/api/v1/docs/` (Swagger).

## Pruebas

```bash
python manage.py test --settings=config.settings.testing
```

**Tipos:** `pip install -r requirements/development.txt` instala los tipos de Django, DRF y openpyxl, y `pyrefly check`
revisa todo el proyecto (hoy sin ningún error). Sin esos paquetes el editor marca como error casi cada línea de las
pruebas (`respuesta.data`, `Modelo.objects`...).

SQLite en memoria; no toca la base local. Las reglas del backend están en `SKILLS_BACKEND.md` y las decisiones en
`docs/estandares/`.

## Producción

- **Despliegue** (Docker, variables de entorno, S3, migración de archivos del sistema anterior, verificación):
  [`docs/despliegue.md`](docs/despliegue.md).
- **Archivos**: bucket privado de S3 (`AWS_STORAGE_BUCKET_NAME`); la base guarda `storage:<clave>` y la dirección
  firmada se calcula al responder (`apps/core/archivos.py`). Sin bucket, van al disco (solo desarrollo).
- **Salud**: `GET /api/v1/salud/` (base de datos y caché), sin sesión, para el balanceador.
- **Logs** a la salida estándar y **Sentry** opcional con `SENTRY_DSN` (no envía datos personales ni cuerpos de
  peticiones): `config/settings/observabilidad.py`.
- **Usuarios finales**: [`docs/manual-de-usuario.md`](docs/manual-de-usuario.md).

Producción se niega a arrancar sin `DJANGO_SECRET_KEY` fuerte y con `REDIS_URL`; Swagger y `/admin/` solo existen en
desarrollo.
