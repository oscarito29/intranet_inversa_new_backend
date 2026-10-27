"""
NOTA: esta app también es responsabilidad de otro trabajo en paralelo que
agrega `Category`, `Upload` y `DocsEtiqueta` (tablas reales `category`,
`upload`, `docs_etiquetas`) para los módulos de Documentos/Categorías/
Políticas. Aquí solo se agregan `Etiqueta`/`EtiquetaRol` (necesarios para
Configuración → pestaña Etiquetas). Si al revisar esto esos otros modelos ya
existen en este archivo, no los dupliques.
"""

from django.db import models

from apps.usuarios.models import Rol


class Etiqueta(models.Model):
    """Tabla `etiqueta`: árbol de 1 nivel (parent_id apunta a otra etiqueta raíz)."""

    id = models.AutoField(primary_key=True)
    etiqueta_nombre = models.CharField(db_column='etiquetaNombre', max_length=100, null=True, blank=True)
    parent = models.ForeignKey('self', db_column='parent_id', null=True, blank=True, on_delete=models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'etiqueta'

    def __str__(self) -> str:
        return self.etiqueta_nombre or ''


class EtiquetaRol(models.Model):
    """Tabla puente `etiqueta_rol`: qué roles pueden ver/usar cada etiqueta."""

    id = models.AutoField(primary_key=True)
    etiqueta = models.ForeignKey(Etiqueta, db_column='etiqueta_id', on_delete=models.DO_NOTHING, related_name='roles')
    rol = models.ForeignKey(Rol, db_column='rol_id', on_delete=models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'etiqueta_rol'


class Category(models.Model):
    """Tabla `category`: clasifica los documentos institucionales (`upload.area`)."""

    # Una categoría inactiva conserva sus documentos pero no admite subir otros nuevos.
    ACTIVA = 'Activo'
    INACTIVA = 'Inactivo'

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=35, unique=True)
    description = models.CharField(max_length=80)
    created_at = models.DateTimeField()
    modified_at = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=50, default=ACTIVA)

    class Meta:
        managed = False
        db_table = 'category'

    def __str__(self) -> str:
        return self.name


class Upload(models.Model):
    """Tabla `upload`: documentos institucionales (no confundir con `product`, remanente roto del legacy)."""

    # Un documento está vigente mientras no haya sido reemplazado. Los datos legados traen
    # además estados sueltos (p. ej. 'E') que también cuentan como vigentes.
    ACTIVO = 'Activo'
    REEMPLAZADO = 'Reemplazado'

    id = models.AutoField(primary_key=True)
    reemplaza_a = models.ForeignKey('self', db_column='reemplaza_a', null=True, blank=True, on_delete=models.DO_NOTHING)
    fname = models.TextField()
    name = models.CharField(max_length=200)
    area = models.ForeignKey(Category, db_column='area', on_delete=models.DO_NOTHING)
    estado = models.CharField(max_length=50)
    fecha = models.DateTimeField()
    tipo = models.CharField(max_length=15)
    tamanio = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'upload'

    def __str__(self) -> str:
        return self.name


class DocsEtiqueta(models.Model):
    """Tabla puente `docs_etiquetas`: etiquetas asignadas a cada documento de `upload`."""

    id = models.AutoField(primary_key=True)
    documento = models.ForeignKey(Upload, db_column='documento_id', on_delete=models.DO_NOTHING, related_name='etiquetas')
    etiqueta = models.ForeignKey(Etiqueta, db_column='etiqueta_id', on_delete=models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'docs_etiquetas'
