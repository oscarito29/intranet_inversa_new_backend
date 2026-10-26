from django.core.exceptions import PermissionDenied

from apps.usuarios.models import Corporacion, Usuario

from .models import Anio, Documento, Mes, RangoFecha
from .permissions import usuario_puede_ver_financiera


def listar_anios():
    return Anio.objects.order_by('-id_anio')


def listar_meses():
    return Mes.objects.order_by('id_mes')


def listar_corporaciones_con_financieras():
    return Corporacion.objects.prefetch_related('financiera_set').order_by('id')


def obtener_rango_vigente() -> RangoFecha | None:
    return RangoFecha.objects.order_by('-id').first()


def contar_notificaciones_pendientes(usuario: Usuario) -> int:
    queryset = Documento.objects.filter(doc_aprobado=Documento.PENDIENTE)
    if usuario.rol_id != 1:
        queryset = queryset.filter(financiera_id=usuario.financiera_id)
    return queryset.count()


def obtener_documentos(usuario: Usuario, anio: int, mes_id: int, corporacion_id: str, financiera_id: str):
    if not usuario_puede_ver_financiera(usuario, financiera_id):
        raise PermissionDenied('No tienes acceso a los documentos de esta financiera.')

    return Documento.objects.filter(
        anio_id=anio,
        mes_id=mes_id,
        corporacion_id=corporacion_id,
        financiera_id=financiera_id,
    ).order_by('-fecha')
