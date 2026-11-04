import re
import tempfile
import zipfile
from typing import IO

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.archivos import leer_archivo
from apps.core.bitacora import registrar_bitacora
from apps.core.cache import invalidar
from apps.usuarios.alcance import puede_subir_a
from apps.usuarios.models import Usuario

from . import selectors
from .models import Anio, Documento, RangoFecha
from .notifications import notificar_aprobacion, notificar_rechazo, notificar_revocacion
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


def _obtener_para_transicion(usuario: Usuario, documento_id: int, permitidos: set[str], accion: str) -> Documento:
    documento = Documento.objects.select_for_update().get(pk=documento_id)
    # Separación de funciones: quien subió un documento no lo aprueba, rechaza ni revoca; lo hace otra persona.
    if (documento.email_usuario_sube or '').strip().lower() == usuario.email.strip().lower():
        raise PermissionDenied(f'No puedes {accion} un documento que subiste tú. Pídeselo a otra persona con permiso para aprobar.')
    if (documento.doc_aprobado or Documento.PENDIENTE) not in permitidos:
        raise ValidationError(f'No se puede {accion} un documento en su estado actual.')
    return documento


def registrar_exportacion_del_periodo(usuario: Usuario, anio_numero: int, mes_id: int, corporacion_id: str) -> None:
    """Sacar los datos de un periodo a un archivo es una acción sensible: queda quién y cuándo."""
    registrar_bitacora(usuario.email, 'Exportacion', f'Exporta a Excel el periodo {mes_id:02d}/{anio_numero} de la corporacion {corporacion_id}')


@transaction.atomic
def subir_documento(
    usuario: Usuario,
    archivo,
    anio: int,
    mes_id: int,
    corporacion_id: str,
    financiera_id: str,
) -> Documento:
    if not puede_subir_a(usuario, financiera_id):
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
    documento = _obtener_para_transicion(usuario, documento_id, ESTADOS_PARA_APROBAR, 'aprobar')
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

    documento = _obtener_para_transicion(usuario, documento_id, ESTADOS_PARA_RECHAZAR, 'rechazar')
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

    documento = _obtener_para_transicion(usuario, documento_id, ESTADOS_PARA_REVOCAR, 'revocar')
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


LIMITE_DEL_ZIP_BYTES = 200 * 1024 * 1024
# Hasta aquí el ZIP se arma en memoria; si pesa más, el archivo temporal pasa a disco.
MEMORIA_DEL_ZIP_BYTES = 16 * 1024 * 1024
_CARACTERES_NO_VALIDOS_EN_NOMBRE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def _nombre_en_zip(financiera: str, estado: str, archivo: str | None) -> str:
    nombre = _CARACTERES_NO_VALIDOS_EN_NOMBRE.sub('_', f'{financiera} - {estado} - {archivo or "documento"}')
    return nombre[:180]


def armar_zip_del_periodo(usuario: Usuario, anio: int, mes_id: int, corporacion_id: str) -> IO[bytes]:
    """
    Un ZIP con el documento vigente (aprobado o pendiente) de cada financiera que la persona puede ver. Lo que el
    servidor no puede leer (el bucket del sistema anterior) no entra, y un `LEEME.txt` dice cuáles faltan. Si el
    periodo pesa más de 200 MB no se arma: se descarga desde la pantalla de uno en uno.
    """
    filas = selectors.documentos_vigentes_del_periodo(usuario, anio, mes_id, corporacion_id)
    if not filas:
        raise ValidationError('No hay documentos vigentes en este periodo para descargar.')

    anio_numero = selectors.obtener_numero_de_anio(anio)
    salida = tempfile.SpooledTemporaryFile(max_size=MEMORIA_DEL_ZIP_BYTES)
    incluidos, sin_leer, total = 0, [], 0
    try:
        with zipfile.ZipFile(salida, 'w', zipfile.ZIP_DEFLATED) as comprimido:
            for fila in filas:
                documento, financiera = fila['documento'], fila['financiera']
                contenido = leer_archivo(documento.ruta_archivo)
                if contenido is None:
                    sin_leer.append(f'{financiera.nombre}: {documento.nombre_archivo}')
                    continue
                total += len(contenido)
                if total > LIMITE_DEL_ZIP_BYTES:
                    raise ValidationError('El periodo pesa más de 200 MB para un solo ZIP. Descarga los documentos de uno en uno desde la pantalla.')
                comprimido.writestr(_nombre_en_zip(financiera.nombre, fila['estado'], documento.nombre_archivo), contenido)
                incluidos += 1
            if sin_leer:
                aviso = 'Estos documentos no se pudieron incluir; ábrelos desde Estados financieros:\n' + '\n'.join(f'- {linea}' for linea in sin_leer)
                comprimido.writestr('LEEME.txt', aviso)
    except BaseException:
        salida.close()
        raise

    if incluidos == 0:
        salida.close()
        raise ValidationError('Los documentos de este periodo no se pueden juntar en un ZIP desde el servidor. Ábrelos desde la pantalla.')

    registrar_bitacora(usuario.email, 'Exportacion', f'Descarga en ZIP el periodo {mes_id:02d}/{anio_numero} de la corporacion {corporacion_id}')
    salida.seek(0)
    return salida
