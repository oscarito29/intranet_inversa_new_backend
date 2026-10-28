from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.core.permissions import Permiso, tiene_permiso
from apps.usuarios.alcance import financieras_visibles, puede_ver_financiera
from apps.usuarios.models import Corporacion, Financiera, Usuario

from .models import Anio, Bitacora, Documento, Mes, RangoFecha

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
    """Quien puede ver todas las entidades ve todo; el resto, solo los de las suyas (ver `apps/usuarios/alcance.py`)."""
    queryset = Documento.objects.all()
    visibles = financieras_visibles(usuario)
    if visibles is not None:
        queryset = queryset.filter(financiera_id__in=visibles)
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
    Campana de la barra superior. Quien puede aprobar ve los documentos que esperan su aprobación; quien sube
    ve los de sus entidades que fueron rechazados o revocados en los últimos 30 días (lo que tiene que corregir);
    quien solo consulta no tiene avisos. `total` cuenta todos; `items` trae solo los 20 más recientes.
    """
    base = _documentos_del_alcance(usuario).select_related('financiera', 'anio', 'mes')

    if tiene_permiso(usuario, Permiso.FINANCIERO_APROBAR):
        pendientes = _pendientes(base).order_by('-fecha')
        items = [_aviso(doc, 'pendiente', doc.fecha, None) for doc in pendientes[:MAX_NOTIFICACIONES]]
        return {'total': pendientes.count(), 'items': items}

    if not tiene_permiso(usuario, Permiso.FINANCIERO_SUBIR):
        return {'total': 0, 'items': []}

    desde = timezone.now() - timedelta(days=DIAS_DE_NOVEDADES)
    rechazados = base.filter(doc_aprobado=Documento.RECHAZADO, fecha_rechaza__gte=desde)
    revocados = base.filter(doc_aprobado=Documento.REVOCADO, fecha_desaprueba__gte=desde)
    items = [_aviso(doc, 'rechazado', doc.fecha_rechaza, doc.motivo_rechazo) for doc in rechazados] + [
        _aviso(doc, 'revocado', doc.fecha_desaprueba, doc.motivo_desaprueba) for doc in revocados
    ]
    items.sort(key=lambda aviso: aviso['fecha'], reverse=True)
    return {'total': len(items), 'items': items[:MAX_NOTIFICACIONES]}


def obtener_documentos(usuario: Usuario, anio: int, mes_id: int, corporacion_id: str, financiera_id: str):
    if not puede_ver_financiera(usuario, financiera_id):
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
    Quien puede ver todas las entidades ve todas las financieras; el resto, solo las suyas.

    "Cargada" es tener un documento pendiente o aprobado. Sin documento, o con el último
    rechazado o revocado, la financiera "falta" por cargar uno válido.
    """
    financieras = Financiera.objects.filter(corporacion_id=corporacion_id).order_by('nombre')
    visibles = financieras_visibles(usuario)
    if visibles is not None:
        financieras = financieras.filter(pk__in=visibles)

    ultimo_por_financiera: dict[str, Documento] = {}
    documentos = Documento.objects.filter(
        anio_id=anio, mes_id=mes_id, corporacion_id=corporacion_id, financiera_id__in=financieras.values('pk')
    ).order_by('fecha', 'id')
    for documento in documentos:
        if documento.financiera_id is not None:
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


def motivo_de_fila(fila: dict) -> str | None:
    """Motivo visible en la fila de un periodo: el del rechazo o el de la revocación, según el estado."""
    documento = fila['documento']
    if documento is None:
        return None
    if fila['estado'] == 'rechazado':
        return documento.motivo_rechazo
    if fila['estado'] == 'revocado':
        return documento.motivo_desaprueba
    return None


ENCABEZADOS_DE_EXPORTACION = ['Financiera', 'Estado', 'Archivo', 'Fecha de subida', 'Motivo']
_ETIQUETA_DE_ESTADO = {
    SIN_CARGAR: 'Sin cargar',
    'pendiente': 'Pendiente',
    'aprobado': 'Aprobado',
    'rechazado': 'Rechazado',
    'revocado': 'Revocado',
}


def filas_de_exportacion_del_periodo(usuario: Usuario, anio: int, mes_id: int, corporacion_id: str) -> list[list]:
    """Una fila por financiera con lo mismo que muestra la pantalla; el alcance (todas o solo las suyas) lo da `obtener_periodo`."""
    filas = []
    for fila in obtener_periodo(usuario, anio, mes_id, corporacion_id)['filas']:
        documento = fila['documento']
        filas.append(
            [
                fila['financiera'].nombre,
                _ETIQUETA_DE_ESTADO[fila['estado']],
                documento.nombre_archivo if documento else None,
                documento.fecha if documento else None,
                motivo_de_fila(fila),
            ]
        )
    return filas


def obtener_numero_de_anio(anio_id: int) -> int:
    return Anio.objects.values_list('anio', flat=True).get(pk=anio_id)


def obtener_historial(usuario: Usuario, documento_id: int) -> list[dict]:
    """
    Línea de tiempo de un documento a partir de sus columnas de evento. La revocación no guarda
    quién la hizo, así que se busca en la bitácora (la entrada que escribe `revocar_documento`).
    """
    documento = get_object_or_404(Documento, pk=documento_id)
    if documento.financiera_id is None:
        raise PermissionDenied('Este documento no tiene una financiera asignada.')
    if not puede_ver_financiera(usuario, documento.financiera_id):
        raise PermissionDenied('No tienes acceso a los documentos de esta financiera.')

    revocacion = (
        Bitacora.objects.filter(descripcion=f'Desaprobación de Estado Financiero {documento.id}').order_by('-fecha').first()
    )
    from datetime import datetime
    eventos: list[tuple[str, datetime | None, str | None, str | None]] = [
        ('subido', documento.fecha, documento.email_usuario_sube, None),
        ('aprobado', documento.fecha_aprueba, documento.email_usuario_aprueba, None),
        ('rechazado', documento.fecha_rechaza, documento.email_usuario_rechaza, documento.motivo_rechazo),
        ('revocado', documento.fecha_desaprueba, revocacion.usuario if revocacion else None, documento.motivo_desaprueba),
    ]
    eventos_con_fecha: list[tuple[str, datetime, str | None, str | None]] = [
        (tipo, fecha, email, motivo)
        for tipo, fecha, email, motivo in eventos
        if fecha is not None
    ]
    return [
        {'tipo': tipo, 'fecha': fecha, 'email': email, 'motivo': motivo}
        for tipo, fecha, email, motivo in sorted(eventos_con_fecha, key=lambda e: e[1])
    ]
