from django.db.models import QuerySet
from django.utils import timezone

from apps.documentos.models import Etiqueta, EtiquetaRol
from apps.usuarios.models import Rol, Usuario

from .models import Actividad, Comunicado, Imagen


def listar_roles() -> QuerySet[Rol]:
    return Rol.objects.all().order_by('id')


def listar_etiquetas() -> QuerySet[Etiqueta]:
    return Etiqueta.objects.all().order_by('id')


def listar_etiqueta_roles() -> QuerySet[EtiquetaRol]:
    return EtiquetaRol.objects.all()


def listar_imagenes() -> QuerySet[Imagen]:
    return Imagen.objects.all().order_by('puesto', 'id')


def listar_comunicados() -> QuerySet[Comunicado]:
    return Comunicado.objects.all().order_by('-fecha_subida', '-id')


def listar_actividades() -> QuerySet[Actividad]:
    return Actividad.objects.all().order_by('fecha')


def listar_cumpleanos_del_mes() -> QuerySet[Usuario]:
    mes_actual = timezone.localdate().month
    return Usuario.objects.filter(fecha_nacimiento__month=mes_actual).order_by('fecha_nacimiento')
