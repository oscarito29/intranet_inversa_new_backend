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
