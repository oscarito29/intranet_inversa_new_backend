from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.core.permissions import ROL_ADMIN
from apps.usuarios.models import Corporacion, Financiera, Usuario

from .models import Anio, Bitacora, Documento, Mes, RangoFecha
from .permissions import usuario_puede_ver_financiera

SIN_CARGAR = 'sin_cargar'

_ESTADO_POR_CODIGO = {
    Documento.PENDIENTE: 'pendiente',
    Documento.APROBADO: 'aprobado',
    Documento.RECHAZADO: 'rechazado',
    Documento.REVOCADO: 'revocado',
}


def listar_anios():
    return Anio.objects.order_by('-id_anio')


def listar_meses():
    return Mes.objects.order_by('id_mes')


def listar_corporaciones_con_financieras():
    return Corporacion.objects.prefetch_related('financiera_set').order_by('id')


def obtener_rango_vigente() -> RangoFecha | None:
    return RangoFecha.objects.order_by('-id').first()


def _documentos_del_alcance(usuario: Usuario):
    """Administradores ven todo; el resto solo los de su financiera."""
    queryset = Documento.objects.all()
    if usuario.rol_id != ROL_ADMIN:
        queryset = queryset.filter(financiera_id=usuario.financiera_id)
    return queryset


def _pendientes(queryset):
    """En la base hay documentos con `doc_aprobado` en NULL y cuentan como pendientes igual que el vacío."""
    return queryset.filter(Q(doc_aprobado=Documento.PENDIENTE) | Q(doc_aprobado__isnull=True))


def contar_pendientes(usuario: Usuario) -> int:
    return _pendientes(_documentos_del_alcance(usuario)).count()


def obtener_resumen(usuario: Usuario) -> dict[str, int]:
    ahora = timezone.now()
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    inicio_semana = (ahora - timedelta(days=ahora.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    queryset = _documentos_del_alcance(usuario)

    return {
        'pendientes': contar_pendientes(usuario),
        'rechazados_mes': queryset.filter(doc_aprobado=Documento.RECHAZADO, fecha_rechaza__gte=inicio_mes).count(),
        'nuevos_semana': queryset.filter(fecha__gte=inicio_semana).count(),
    }


MAX_NOTIFICACIONES = 20
DIAS_DE_NOVEDADES = 30


def _aviso(documento: Documento, tipo: str, fecha, motivo: str | None) -> dict:
    return {'documento': documento, 'tipo': tipo, 'fecha': fecha, 'motivo': motivo}


def obtener_notificaciones(usuario: Usuario) -> dict:
    """
    Campana de la barra superior. El administrador ve los documentos que esperan su aprobación;
    el resto, los de su financiera que fueron rechazados o revocados en los últimos 30 días
    (lo que tiene que corregir). `total` cuenta todos; `items` trae solo los 20 más recientes.
    """
    base = _documentos_del_alcance(usuario).select_related('financiera', 'anio', 'mes')

    if usuario.rol_id == ROL_ADMIN:
        pendientes = _pendientes(base).order_by('-fecha')
        items = [_aviso(doc, 'pendiente', doc.fecha, None) for doc in pendientes[:MAX_NOTIFICACIONES]]
        return {'total': pendientes.count(), 'items': items}

    desde = timezone.now() - timedelta(days=DIAS_DE_NOVEDADES)
    rechazados = base.filter(doc_aprobado=Documento.RECHAZADO, fecha_rechaza__gte=desde)
    revocados = base.filter(doc_aprobado=Documento.REVOCADO, fecha_desaprueba__gte=desde)
    items = [_aviso(doc, 'rechazado', doc.fecha_rechaza, doc.motivo_rechazo) for doc in rechazados] + [
        _aviso(doc, 'revocado', doc.fecha_desaprueba, doc.motivo_desaprueba) for doc in revocados
    ]
    items.sort(key=lambda aviso: aviso['fecha'], reverse=True)
    return {'total': len(items), 'items': items[:MAX_NOTIFICACIONES]}


def obtener_documentos(usuario: Usuario, anio: int, mes_id: int, corporacion_id: str, financiera_id: str):
    if not usuario_puede_ver_financiera(usuario, financiera_id):
        raise PermissionDenied('No tienes acceso a los documentos de esta financiera.')

    return Documento.objects.filter(
        anio_id=anio,
        mes_id=mes_id,
        corporacion_id=corporacion_id,
        financiera_id=financiera_id,
    ).order_by('-fecha')


def estado_de(documento: Documento) -> str:
    """Nombre del estado; en la base hay documentos con `doc_aprobado` en NULL y cuentan como pendientes."""
    return _ESTADO_POR_CODIGO.get(documento.doc_aprobado or Documento.PENDIENTE, 'pendiente')


def obtener_periodo(usuario: Usuario, anio: int, mes_id: int, corporacion_id: str) -> dict:
    """
    Estado de cada financiera de una corporación en un periodo, con su documento más reciente.
    El administrador ve todas las financieras; el resto, solo la suya.

    "Cargada" es tener un documento pendiente o aprobado. Sin documento, o con el último
    rechazado o revocado, la financiera "falta" por cargar uno válido.
    """
    financieras = Financiera.objects.filter(corporacion_id=corporacion_id).order_by('nombre')
    if usuario.rol_id != ROL_ADMIN:
        financieras = financieras.filter(pk=usuario.financiera_id)

    ultimo_por_financiera: dict[str, Documento] = {}
    documentos = Documento.objects.filter(
        anio_id=anio, mes_id=mes_id, corporacion_id=corporacion_id, financiera_id__in=financieras.values('pk')
    ).order_by('fecha', 'id')
    for documento in documentos:
        ultimo_por_financiera[documento.financiera_id] = documento

    filas = []
    por_estado = {SIN_CARGAR: 0, 'pendiente': 0, 'aprobado': 0, 'rechazado': 0, 'revocado': 0}
    for financiera in financieras:
        documento = ultimo_por_financiera.get(financiera.pk)
        estado = estado_de(documento) if documento else SIN_CARGAR
        por_estado[estado] += 1
        filas.append({'financiera': financiera, 'estado': estado, 'documento': documento})

    cargadas = por_estado['pendiente'] + por_estado['aprobado']
    return {
        'filas': filas,
        'resumen': {'total': len(filas), 'cargadas': cargadas, 'faltan': len(filas) - cargadas, 'por_estado': por_estado},
    }


def obtener_historial(usuario: Usuario, documento_id: int) -> list[dict]:
    """
    Línea de tiempo de un documento a partir de sus columnas de evento. La revocación no guarda
    quién la hizo, así que se busca en la bitácora (la entrada que escribe `revocar_documento`).
    """
    documento = get_object_or_404(Documento, pk=documento_id)
    if not usuario_puede_ver_financiera(usuario, documento.financiera_id):
        raise PermissionDenied('No tienes acceso a los documentos de esta financiera.')

    revocacion = (
        Bitacora.objects.filter(descripcion=f'Desaprobación de Estado Financiero {documento.id}').order_by('-fecha').first()
    )
    eventos = [
        ('subido', documento.fecha, documento.email_usuario_sube, None),
        ('aprobado', documento.fecha_aprueba, documento.email_usuario_aprueba, None),
        ('rechazado', documento.fecha_rechaza, documento.email_usuario_rechaza, documento.motivo_rechazo),
        ('revocado', documento.fecha_desaprueba, revocacion.usuario if revocacion else None, documento.motivo_desaprueba),
    ]
    return [
        {'tipo': tipo, 'fecha': fecha, 'email': email, 'motivo': motivo}
        for tipo, fecha, email, motivo in sorted((e for e in eventos if e[1] is not None), key=lambda e: e[1])
    ]
