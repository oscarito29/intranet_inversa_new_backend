from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.usuarios.models import Usuario

from .models import Bitacora, Documento, RangoFecha
from .notifications import notificar_aprobacion, notificar_rechazo, notificar_revocacion
from .permissions import usuario_puede_ver_financiera
from .storage import guardar_documento


def _registrar_bitacora(usuario_email: str, accion: str, descripcion: str) -> None:
    Bitacora.objects.create(
        usuario=usuario_email,
        accion=accion,
        descripcion=descripcion[:100],
        fecha=timezone.now(),
    )


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

    _registrar_bitacora(usuario.email, 'Creacion', f'Sube el documento {archivo.name}'[:100])
    return documento


def _requerir_admin(usuario: Usuario) -> None:
    if usuario.rol_id != 1:
        raise PermissionDenied('Solo un administrador puede realizar esta acción.')


def aprobar_documento(usuario: Usuario, documento_id: int) -> Documento:
    _requerir_admin(usuario)
    documento = Documento.objects.get(pk=documento_id)
    documento.doc_aprobado = Documento.APROBADO
    documento.email_usuario_aprueba = usuario.email
    documento.fecha_aprueba = timezone.now()
    documento.save(update_fields=['doc_aprobado', 'email_usuario_aprueba', 'fecha_aprueba'])

    _registrar_bitacora(usuario.email, 'Aprobacion', f'Aprueba documento subido id número {documento.id}')
    notificar_aprobacion(documento)
    return documento


def rechazar_documento(usuario: Usuario, documento_id: int, motivo: str) -> Documento:
    _requerir_admin(usuario)
    if not motivo:
        raise ValidationError('El motivo es requerido.')

    documento = Documento.objects.get(pk=documento_id)
    documento.doc_aprobado = Documento.RECHAZADO
    documento.email_usuario_rechaza = usuario.email
    documento.motivo_rechazo = motivo
    documento.fecha_rechaza = timezone.now()
    documento.save(update_fields=['doc_aprobado', 'email_usuario_rechaza', 'motivo_rechazo', 'fecha_rechaza'])

    _registrar_bitacora(usuario.email, 'Rechazo', f'Rechaza documento subido id número {documento.id}')
    notificar_rechazo(documento)
    return documento


def revocar_documento(usuario: Usuario, documento_id: int, motivo: str) -> Documento:
    _requerir_admin(usuario)
    if not motivo:
        raise ValidationError('El motivo es requerido.')

    documento = Documento.objects.get(pk=documento_id)
    documento.doc_aprobado = Documento.REVOCADO
    documento.motivo_desaprueba = motivo
    documento.fecha_desaprueba = timezone.now()
    documento.save(update_fields=['doc_aprobado', 'motivo_desaprueba', 'fecha_desaprueba'])

    _registrar_bitacora(usuario.email, 'Edicion', f'Desaprobación de Estado Financiero {documento.id}'[:100])
    notificar_revocacion(documento)
    return documento


def guardar_rango_fechas(usuario: Usuario, desde, hasta) -> RangoFecha:
    _requerir_admin(usuario)
    rango = RangoFecha.objects.create(
        desde=desde,
        hasta=hasta,
        email_usuario=usuario.email,
        fecha_modifica=timezone.now(),
    )
    _registrar_bitacora(usuario.email, 'Edicion', 'Modifica la fecha de Subida de Documentos')
    return rango
