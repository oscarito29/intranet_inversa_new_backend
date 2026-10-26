from django.db import models


class Imagen(models.Model):
    """Tabla `imagenes`: carrusel institucional del Dashboard (4 puestos)."""

    id = models.AutoField(primary_key=True)
    archivo = models.CharField(max_length=255, null=True, blank=True)
    ruta_img = models.CharField(max_length=350, null=True, blank=True)
    puesto = models.IntegerField(null=True, blank=True)
    creado_en = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'imagenes'


class Comunicado(models.Model):
    """Tabla `comunicados`: anuncios mostrados en el Dashboard."""

    id = models.AutoField(primary_key=True)
    titulo = models.CharField(max_length=100, null=True, blank=True)
    contenido = models.CharField(max_length=700, null=True, blank=True)
    imagen = models.CharField(max_length=500)
    usuario_sube = models.CharField(max_length=50, null=True, blank=True)
    fecha_subida = models.DateField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'comunicados'


class Actividad(models.Model):
    """Tabla `actividades`: calendario de actividades del Dashboard."""

    id = models.AutoField(primary_key=True)
    fecha = models.DateField()
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(null=True, blank=True)
    hora_desde = models.TimeField(null=True, blank=True)
    hora_hasta = models.TimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'actividades'
