from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.core.permissions import Permiso, tiene_permiso
from apps.usuarios.alcance import financieras_visibles, puede_subir_a, puede_ver_financiera
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


MAX_FALTANTES = 5


def _mes_que_se_cierra(hoy: date) -> tuple[int, int]:
    """Los estados de un mes se suben al mes siguiente: el que se cierra es el anterior al actual."""
    ultimo_dia_del_anterior = hoy.replace(day=1) - timedelta(days=1)
    return ultimo_dia_del_anterior.year, ultimo_dia_del_anterior.month


def _ventana_de_subida(hoy: date) -> dict | None:
    """
    La última ventana configurada y cómo está hoy. `dias` son los que quedan para que cierre (si está abierta,
    0 es que cierra hoy) o los que faltan para que abra (si es próxima); una ventana cerrada no tiene días.
    """
    rango = obtener_rango_vigente()
    if rango is None:
        return None
    if hoy < rango.desde:
        estado, dias = 'proxima', (rango.desde - hoy).days
    elif hoy > rango.hasta:
        estado, dias = 'cerrada', None
    else:
        estado, dias = 'abierta', (rango.hasta - hoy).days
    return {'desde': rango.desde, 'hasta': rango.hasta, 'estado': estado, 'dias': dias}


def obtener_panorama(usuario: Usuario, hoy: date | None = None) -> dict:
    """
    El cierre del mes anterior, para el Dashboard: cómo va cada corporación (según lo que la persona puede ver),
    la ventana de subida y, para quien sube, las entidades suyas que todavía no cargaron nada ese mes.
    Es la misma cuenta que Estados financieros (`obtener_periodo`), así que ambas pantallas coinciden.
    """
    hoy = hoy or timezone.localdate()
    anio_numero, mes_id = _mes_que_se_cierra(hoy)
    anio = Anio.objects.filter(anio=anio_numero).first()
    mes = Mes.objects.filter(pk=mes_id).first()
    # Sin el año en el catálogo no puede haber documentos: todo cuenta como sin cargar.
    anio_id = anio.id_anio if anio else 0
    puede_subir = tiene_permiso(usuario, Permiso.FINANCIERO_SUBIR)

    corporaciones, faltan = [], []
    for corporacion in Corporacion.objects.order_by('id'):
        periodo = obtener_periodo(usuario, anio_id, mes_id, corporacion.pk)
        if periodo['resumen']['total'] == 0:
            continue
        corporaciones.append({'id': corporacion.pk, 'nombre': corporacion.tipo_corporacion, **periodo['resumen']})
        if puede_subir:
            faltan += [
                {'financiera_id': fila['financiera'].pk, 'financiera_nombre': fila['financiera'].nombre, 'corporacion_id': corporacion.pk}
                for fila in periodo['filas']
                if fila['estado'] == SIN_CARGAR and puede_subir_a(usuario, fila['financiera'].pk)
            ]

    return {
        'periodo': {'anio_id': anio_id, 'anio_numero': anio_numero, 'mes_id': mes_id, 'mes_nombre': mes.mes if mes else str(mes_id)},
        'ventana': _ventana_de_subida(hoy),
        'corporaciones': corporaciones,
        'faltan': {'total': len(faltan), 'items': faltan[:MAX_FALTANTES]},
    }


def documentos_vigentes_del_periodo(usuario: Usuario, anio: int, mes_id: int, corporacion_id: str) -> list[dict]:
    """El documento más reciente de cada financiera que tiene uno aprobado o pendiente (los «vigentes» de la pantalla)."""
    return [
        {'financiera': fila['financiera'], 'estado': fila['estado'], 'documento': fila['documento']}
        for fila in obtener_periodo(usuario, anio, mes_id, corporacion_id)['filas']
        if fila['documento'] is not None and fila['estado'] in ('pendiente', 'aprobado')
    ]


MIN_CARACTERES_DE_BUSQUEDA = 2
MAX_RESULTADOS_DE_BUSQUEDA = 8


def buscar_documentos(usuario: Usuario, texto: str) -> list[Documento]:
    """
    Estados financieros por nombre de archivo o de financiera, los más recientes primero y solo de las entidades que
    la persona puede ver. Con menos de dos letras no busca. Los documentos sin financiera, año o mes (hay en la base
    heredada) no se ofrecen porque no hay a dónde llevar a quien los elija.
    """
    texto = texto.strip()
    if len(texto) < MIN_CARACTERES_DE_BUSQUEDA:
        return []
    coincidencias = _documentos_del_alcance(usuario).filter(
        Q(nombre_archivo__icontains=texto) | Q(financiera__nombre__icontains=texto),
        financiera__isnull=False,
        anio__isnull=False,
        mes__isnull=False,
    )
    return list(coincidencias.select_related('financiera', 'anio', 'mes').order_by('-fecha', '-id')[:MAX_RESULTADOS_DE_BUSQUEDA])
