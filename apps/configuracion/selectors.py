from datetime import date, datetime, time, timedelta

from django.core.paginator import Paginator
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.documentos.models import Etiqueta, EtiquetaRol
from apps.financial.models import Bitacora
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


def mes_actual() -> int:
    return timezone.localdate().month


def listar_cumpleanos_del_mes() -> QuerySet[Usuario]:
    return Usuario.objects.filter(fecha_nacimiento__month=mes_actual()).order_by('fecha_nacimiento')


TAMANIO_PAGINA_BITACORA_MAXIMO = 100


def listar_acciones_de_bitacora() -> list[str]:
    return list(Bitacora.objects.order_by('accion').values_list('accion', flat=True).distinct())


def obtener_pagina_de_bitacora(
    texto: str = '',
    accion: str = '',
    desde: date | None = None,
    hasta: date | None = None,
    pagina: int = 1,
    tamanio: int = 25,
) -> dict:
    """
    Una página de la bitácora, de lo más reciente a lo más antiguo. `texto` busca en la persona y en la descripción;
    `desde` y `hasta` son días completos (el último incluido). El id desempata para que las páginas no se mezclen.
    """
    consulta = Bitacora.objects.all()
    if texto:
        consulta = consulta.filter(Q(usuario__icontains=texto) | Q(descripcion__icontains=texto))
    if accion:
        consulta = consulta.filter(accion=accion)
    if desde:
        consulta = consulta.filter(fecha__gte=timezone.make_aware(datetime.combine(desde, time.min)))
    if hasta:
        consulta = consulta.filter(fecha__lt=timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min)))

    paginador = Paginator(consulta.order_by('-fecha', '-id'), min(max(tamanio, 1), TAMANIO_PAGINA_BITACORA_MAXIMO))
    pagina_actual = paginador.get_page(pagina)
    return {
        'registros': list(pagina_actual.object_list),
        'total': paginador.count,
        'pagina': pagina_actual.number,
        'tamanio': paginador.per_page,
        'paginas': paginador.num_pages,
    }
