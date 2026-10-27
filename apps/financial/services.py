from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.bitacora import registrar_bitacora
from apps.core.cache import invalidar
from apps.usuarios.models import Usuario

from . import selectors
from .models import Anio, Documento, RangoFecha
from .notifications import notificar_aprobacion, notificar_rechazo, notificar_revocacion
from .permissions import usuario_puede_ver_financiera
from .storage import guardar_documento

# Estados desde los que se permite cada acción. Revocar también aplica a un documento
# rechazado porque la pantalla ofrece esa acción en ambos casos.
ESTADOS_PARA_APROBAR = {Documento.PENDIENTE}
ESTADOS_PARA_RECHAZAR = {Documento.PENDIENTE}
ESTADOS_PARA_REVOCAR = {Documento.APROBADO, Documento.RECHAZADO}


def _asegurar_anios(desde: int, hasta: int) -> None:
    """Los documentos se suben a un año del catálogo; abrir una ventana en un año nuevo lo crea (id = año, como en los existentes)."""
    for anio in range(desde, hasta + 1):
        Anio.objects.get_or_create(id_anio=anio, defaults={'anio': anio})


def _validar_ventana_de_subida() -> None:
    rango = selectors.obtener_rango_vigente()
    hoy = timezone.localdate()
    if rango is None or not (rango.desde <= hoy <= rango.hasta):
        raise ValidationError('La subida de documentos no está habilitada en esta fecha.')


def _obtener_para_transicion(documento_id: int, permitidos: set[str], accion: str) -> Documento:
    documento = Documento.objects.select_for_update().get(pk=documento_id)
    if (documento.doc_aprobado or Documento.PENDIENTE) not in permitidos:
        raise ValidationError(f'No se puede {accion} un documento en su estado actual.')
    return documento


@transaction.atomic
def subir_documento(
    usuario: Usuario,
    archivo,
    anio: int,
    mes_id: int,
    corporacion_id: str,
    financiera_id: str,
) -> Documento:
    if not usuario_puede_ver_financiera(usuario, financiera_id):
        raise PermissionDenied('No tienes acceso a esta financiera.')
    _validar_ventana_de_subida()

    url_archivo = guardar_documento(archivo, corporacion_id, financiera_id, anio, mes_id)

    documento = Documento.objects.create(
        nombre_archivo=archivo.name,
        ruta_archivo=url_archivo,
        doc_aprobado=Documento.PENDIENTE,
        anio_id=anio,
        mes_id=mes_id,
        corporacion_id=corporacion_id,
        financiera_id=financiera_id,
        fecha=timezone.now(),
        email_usuario_sube=usuario.email,
    )

    registrar_bitacora(usuario.email, 'Creacion', f'Sube el documento {archivo.name}')
    return documento


@transaction.atomic
def aprobar_documento(usuario: Usuario, documento_id: int) -> Documento:
    documento = _obtener_para_transicion(documento_id, ESTADOS_PARA_APROBAR, 'aprobar')
    documento.doc_aprobado = Documento.APROBADO
    documento.email_usuario_aprueba = usuario.email
    documento.fecha_aprueba = timezone.now()
    documento.save(update_fields=['doc_aprobado', 'email_usuario_aprueba', 'fecha_aprueba'])

    registrar_bitacora(usuario.email, 'Aprobacion', f'Aprueba documento subido id número {documento.id}')
    transaction.on_commit(lambda: notificar_aprobacion(documento))
    return documento


@transaction.atomic
def rechazar_documento(usuario: Usuario, documento_id: int, motivo: str) -> Documento:
    if not motivo:
        raise ValidationError({'motivo': 'El motivo es requerido.'})

    documento = _obtener_para_transicion(documento_id, ESTADOS_PARA_RECHAZAR, 'rechazar')
    documento.doc_aprobado = Documento.RECHAZADO
    documento.email_usuario_rechaza = usuario.email
    documento.motivo_rechazo = motivo
    documento.fecha_rechaza = timezone.now()
    documento.save(update_fields=['doc_aprobado', 'email_usuario_rechaza', 'motivo_rechazo', 'fecha_rechaza'])

    registrar_bitacora(usuario.email, 'Rechazo', f'Rechaza documento subido id número {documento.id}')
    transaction.on_commit(lambda: notificar_rechazo(documento))
    return documento


@transaction.atomic
def revocar_documento(usuario: Usuario, documento_id: int, motivo: str) -> Documento:
    if not motivo:
        raise ValidationError({'motivo': 'El motivo es requerido.'})

    documento = _obtener_para_transicion(documento_id, ESTADOS_PARA_REVOCAR, 'revocar')
    documento.doc_aprobado = Documento.REVOCADO
    documento.motivo_desaprueba = motivo
    documento.fecha_desaprueba = timezone.now()
    documento.save(update_fields=['doc_aprobado', 'motivo_desaprueba', 'fecha_desaprueba'])

    registrar_bitacora(usuario.email, 'Edicion', f'Desaprobación de Estado Financiero {documento.id}')
    transaction.on_commit(lambda: notificar_revocacion(documento))
    return documento


@transaction.atomic
def guardar_rango_fechas(usuario: Usuario, desde, hasta) -> RangoFecha:
    if desde > hasta:
        raise ValidationError({'hasta': 'La fecha final no puede ser anterior a la inicial.'})
    rango = RangoFecha.objects.create(
        desde=desde,
        hasta=hasta,
        email_usuario=usuario.email,
        fecha_modifica=timezone.now(),
    )
    _asegurar_anios(desde.year, hasta.year)
    registrar_bitacora(usuario.email, 'Edicion', 'Modifica la fecha de Subida de Documentos')
    invalidar('financiero')
    return rango
