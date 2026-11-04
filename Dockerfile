# Imagen de producción del backend: gunicorn, usuario sin privilegios, sin claves dentro de la imagen.
# Todo lo de configuración llega por variables de entorno (ver .env.example, sección "Solo producción").
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# Las dependencias van primero: mientras requirements/ no cambie, esta capa se reutiliza.
COPY requirements ./requirements
RUN pip install -r requirements/production.txt

COPY . .

# `media/` solo se usa si no hay bucket de S3 (AWS_STORAGE_BUCKET_NAME): es la carpeta que se monta como volumen.
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /app/media \
    && chown app:app /app/media
USER app

EXPOSE 8000

# Pregunta a /api/v1/salud/ (base de datos y caché). Usa el primer host permitido, porque Django rechaza
# cualquier otro encabezado Host.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8000/api/v1/salud/', headers={'Host': os.environ['DJANGO_ALLOWED_HOSTS'].split(',')[0]}), timeout=4)"

# WEB_CONCURRENCY = procesos; con 2 a 4 sobra para una intranet de decenas de usuarios.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-"]
