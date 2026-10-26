from django.db import models

from apps.usuarios.models import Corporacion, Financiera

__all__ = ['Anio', 'Mes', 'Documento', 'RangoFecha', 'DestinatarioCorreo', 'Bitacora']


class Anio(models.Model):
    id_anio = models.IntegerField(primary_key=True)
    anio = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'anio'

    def __str__(self) -> str:
        return str(self.anio)


class Mes(models.Model):
    id_mes = models.IntegerField(primary_key=True)
    mes = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = 'mes'

    def __str__(self) -> str:
        return self.mes


class Documento(models.Model):
    """Tabla `documentos`: estados financieros subidos por financiera/periodo."""

    PENDIENTE = ''
    RECHAZADO = '0'
    APROBADO = '1'
    REVOCADO = '2'

    id = models.AutoField(primary_key=True)
    nombre_archivo = models.CharField(max_length=255, null=True, blank=True)
    ruta_archivo = models.TextField(null=True, blank=True)
    doc_aprobado = models.CharField(max_length=4, null=True, blank=True)
    anio = models.ForeignKey(Anio, db_column='anio', on_delete=models.DO_NOTHING, null=True)
    mes = models.ForeignKey(Mes, db_column='mes_id', on_delete=models.DO_NOTHING, null=True)
    corporacion = models.ForeignKey(Corporacion, db_column='id_corporacion', on_delete=models.DO_NOTHING, null=True)
    financiera = models.ForeignKey(Financiera, db_column='financiera_id', on_delete=models.DO_NOTHING, null=True)
    fecha = models.DateTimeField(null=True, blank=True)
    email_usuario_sube = models.CharField(db_column='emailUsuario_sube', max_length=255, null=True, blank=True)
    email_usuario_aprueba = models.CharField(db_column='emailUsuario_aprueba', max_length=100, null=True, blank=True)
    fecha_aprueba = models.DateTimeField(null=True, blank=True)
    email_usuario_rechaza = models.CharField(db_column='emailUsuario_rechaza', max_length=100, null=True, blank=True)
    motivo_rechazo = models.CharField(db_column='motivoRechazo', max_length=700, null=True, blank=True)
    fecha_rechaza = models.DateTimeField(null=True, blank=True)
    motivo_desaprueba = models.CharField(max_length=350, null=True, blank=True)
    fecha_desaprueba = models.DateTimeField(db_column='fecha_Desaprueba', null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'documentos'

    def __str__(self) -> str:
        return self.nombre_archivo or f'Documento {self.id}'


class RangoFecha(models.Model):
    id = models.AutoField(primary_key=True)
    desde = models.DateField()
    hasta = models.DateField()
    email_usuario = models.CharField(db_column='emailUsuario', max_length=100)
    fecha_modifica = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'rangofecha'

    def __str__(self) -> str:
        return f'{self.desde} - {self.hasta}'


class DestinatarioCorreo(models.Model):
    """Sin PK real en la tabla; se usa el email como PK conceptual en Django (no afecta managed=False)."""

    email_destinatario = models.CharField(db_column='emailDestinatario', max_length=50, primary_key=True)
    estado = models.BooleanField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'destinatariocorreo'

    def __str__(self) -> str:
        return self.email_destinatario


class Bitacora(models.Model):
    id = models.AutoField(primary_key=True)
    usuario = models.CharField(max_length=100)
    accion = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=100)
    fecha = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'bitacora'

    def __str__(self) -> str:
        return f'{self.usuario} - {self.accion}'
