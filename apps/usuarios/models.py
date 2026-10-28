from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class Corporacion(models.Model):
    """Tabla `corporacion`: agrupa financieras (001 Financieras, 002 Otros, 003 Unificados)."""

    id = models.CharField(max_length=11, primary_key=True)
    tipo_corporacion = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'corporacion'

    def __str__(self) -> str:
        return self.tipo_corporacion


class Financiera(models.Model):
    """Tabla `financieras`: entidad/agencia a la que pertenece un usuario."""

    id = models.CharField(max_length=11, primary_key=True)
    nombre = models.CharField(max_length=100)
    corporacion = models.ForeignKey(Corporacion, db_column='id_corporacion', on_delete=models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'financieras'

    def __str__(self) -> str:
        return self.nombre


class Rol(models.Model):
    """Tabla `rol`. Hoy solo existen 1=Admin y 2=User en los datos reales."""

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=15)

    class Meta:
        managed = False
        db_table = 'rol'

    def __str__(self) -> str:
        return self.name


class UsuarioManager(BaseUserManager['Usuario']):
    def get_by_natural_key(self, username: str | None) -> 'Usuario':
        return self.get(**{self.model.USERNAME_FIELD: self.normalize_email(username)})


class Usuario(AbstractBaseUser):
    """
    Mapea la tabla `user` existente (legacy, managed=False). El hash de password
    guardado hoy es MD5 sin salt; ver PASSWORD_HASHERS en settings para la
    compatibilidad/migración transparente a Argon2.
    """

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=30)
    email = models.EmailField(max_length=255, unique=True)
    # `password` lo hereda de AbstractBaseUser. La tabla `user` legacy no
    # tiene columna `last_login`: se elimina el campo heredado por completo
    # (patrón soportado por Django: asignar None a un campo heredado de una
    # base abstracta lo remueve del modelo concreto).
    last_login = None  # type: ignore[assignment]
    full_name = models.CharField(max_length=160)
    phone_number = models.CharField(max_length=15)
    address = models.CharField(max_length=255)
    picture = models.CharField(max_length=255, null=True, blank=True)
    rol = models.ForeignKey(Rol, db_column='rol_id', on_delete=models.DO_NOTHING, default=1)
    created_at = models.DateTimeField(null=True, blank=True)
    remember_token = models.CharField(max_length=255, null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=10, null=True, blank=True)
    financiera = models.ForeignKey(Financiera, db_column='userFinancieraId', on_delete=models.DO_NOTHING)
    marca_id = models.CharField(db_column='marcaId', max_length=13, null=True, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)

    objects = UsuarioManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        managed = False
        db_table = 'user'

    def __str__(self) -> str:
        return self.email

    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return self.estado == 'A'

    @property
    def is_staff(self) -> bool:
        return self.rol_id == 1

    def has_perm(self, perm: str, obj=None) -> bool:
        return self.rol_id == 1

    def has_module_perms(self, app_label: str) -> bool:
        return self.rol_id == 1


class UsuarioEntidad(models.Model):
    """
    Tabla NUEVA `usuario_entidad` (la crea una migración de Django; el sistema PHP no la conoce): las entidades
    ADICIONALES de una persona. Su entidad principal sigue en `user.userFinancieraId`.

    Sin restricciones de clave foránea en la base (`db_constraint=False`): los tipos y la colación de las tablas
    heredadas no siempre coinciden y MySQL se niega a crear la restricción. La integridad la cuida el servicio.
    """

    usuario = models.ForeignKey(Usuario, db_column='usuario_id', on_delete=models.CASCADE, related_name='entidades_adicionales', db_constraint=False)
    financiera = models.ForeignKey(Financiera, db_column='financiera_id', on_delete=models.DO_NOTHING, related_name='+', db_constraint=False)

    class Meta:
        db_table = 'usuario_entidad'
        constraints = [models.UniqueConstraint(fields=['usuario', 'financiera'], name='usuario_entidad_unica')]

    def __str__(self) -> str:
        return f'{self.usuario_id} - {self.financiera_id}'
