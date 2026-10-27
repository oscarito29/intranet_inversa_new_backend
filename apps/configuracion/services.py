from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from apps.core.archivos import borrar_archivo_local
from apps.core.bitacora import registrar_bitacora
from apps.core.cache import invalidar
from apps.documentos.models import DocsEtiqueta, Etiqueta, EtiquetaRol
from apps.usuarios.models import Usuario

from . import storage
from .models import Actividad, Comunicado, Imagen

PUESTOS_CARRUSEL = (1, 2, 3, 4)


@transaction.atomic
def crear_imagen_carrusel(archivo: UploadedFile) -> Imagen:
    ocupados = set(Imagen.objects.select_for_update().values_list('puesto', flat=True))
    libres = [puesto for puesto in PUESTOS_CARRUSEL if puesto not in ocupados]
    if not libres:
        raise ValidationError({'file': f'El carrusel admite como máximo {len(PUESTOS_CARRUSEL)} imágenes.'})

    ruta = storage.guardar_imagen_carrusel(archivo)
    imagen = Imagen.objects.create(archivo=archivo.name, ruta_img=ruta, puesto=libres[0], creado_en=timezone.now())
    invalidar('configuracion-imagenes')
    return imagen


@transaction.atomic
def actualizar_puesto_imagen(imagen_id: int, puesto: int) -> Imagen:
    """Si otra imagen ya ocupa el puesto pedido, intercambian lugares (los puestos no se repiten)."""
    if puesto not in PUESTOS_CARRUSEL:
        raise ValidationError({'puesto': 'El puesto debe ser un número del 1 al 4.'})

    imagen = Imagen.objects.select_for_update().get(pk=imagen_id)
    puesto_anterior = imagen.puesto
    ocupante = Imagen.objects.filter(puesto=puesto).exclude(pk=imagen_id).first()
    if ocupante is not None:
        ocupante.puesto = puesto_anterior
        ocupante.save(update_fields=['puesto'])

    imagen.puesto = puesto
    imagen.save(update_fields=['puesto'])
    invalidar('configuracion-imagenes')
    return imagen


@transaction.atomic
def eliminar_imagen(imagen_id: int) -> None:
    imagen = Imagen.objects.get(pk=imagen_id)
    ruta = imagen.ruta_img
    imagen.delete()
    borrar_archivo_local(ruta)
    invalidar('configuracion-imagenes')


@transaction.atomic
def guardar_comunicado(
    usuario: Usuario,
    comunicado_id: int | None,
    titulo: str,
    contenido: str,
    archivo: UploadedFile | None,
) -> Comunicado:
    if comunicado_id:
        comunicado = Comunicado.objects.get(pk=comunicado_id)
        imagen_anterior = comunicado.imagen
        comunicado.titulo = titulo
        comunicado.contenido = contenido
        if archivo is not None:
            comunicado.imagen = storage.guardar_imagen_comunicado(archivo)
        comunicado.save()
        if archivo is not None:
            borrar_archivo_local(imagen_anterior)
    else:
        if archivo is None:
            raise ValidationError({'file': 'Se requiere una imagen para publicar un comunicado nuevo.'})
        comunicado = Comunicado.objects.create(
            titulo=titulo,
            contenido=contenido,
            imagen=storage.guardar_imagen_comunicado(archivo),
            usuario_sube=usuario.email,
            fecha_subida=timezone.localdate(),
        )

    invalidar('configuracion-comunicados')
    return comunicado


@transaction.atomic
def eliminar_comunicado(comunicado_id: int) -> None:
    comunicado = Comunicado.objects.get(pk=comunicado_id)
    ruta = comunicado.imagen
    comunicado.delete()
    borrar_archivo_local(ruta)
    invalidar('configuracion-comunicados')


@transaction.atomic
def crear_actividad(usuario: Usuario, fecha, titulo: str, descripcion: str, hora_desde, hora_hasta) -> Actividad:
    actividad = Actividad.objects.create(
        fecha=fecha, titulo=titulo, descripcion=descripcion, hora_desde=hora_desde, hora_hasta=hora_hasta
    )
    registrar_bitacora(usuario.email, 'Creacion', f'Crea la actividad {titulo}')
    invalidar('configuracion-actividades')
    return actividad


@transaction.atomic
def actualizar_actividad(usuario: Usuario, actividad_id: int, datos: dict) -> Actividad:
    """Solo cambia los campos que llegan; la validación cruzada de horas se hace con los valores finales."""
    actividad = Actividad.objects.select_for_update().get(pk=actividad_id)
    for campo, valor in datos.items():
        setattr(actividad, campo, valor)
    if actividad.hora_desde and actividad.hora_hasta and actividad.hora_hasta < actividad.hora_desde:
        raise ValidationError({'hora_hasta': 'La hora final no puede ser anterior a la inicial.'})
    actividad.save()
    registrar_bitacora(usuario.email, 'Edicion', f'Modifica la actividad {actividad.titulo}')
    invalidar('configuracion-actividades')
    return actividad


@transaction.atomic
def eliminar_actividad(usuario: Usuario, actividad_id: int) -> None:
    actividad = Actividad.objects.get(pk=actividad_id)
    titulo = actividad.titulo
    actividad.delete()
    registrar_bitacora(usuario.email, 'Eliminacion', f'Elimina la actividad {titulo}')
    invalidar('configuracion-actividades')


@transaction.atomic
def guardar_etiqueta(etiqueta_id: int | None, etiqueta_nombre: str, parent_id: int | None, roles_permitidos: list[int]) -> Etiqueta:
    if parent_id is not None:
        if parent_id == etiqueta_id:
            raise ValidationError({'parent_id': 'Una etiqueta no puede ser su propia etiqueta padre.'})
        if not Etiqueta.objects.filter(pk=parent_id).exists():
            raise ValidationError({'parent_id': 'La etiqueta padre no existe.'})

    if etiqueta_id:
        etiqueta = Etiqueta.objects.get(pk=etiqueta_id)
        etiqueta.etiqueta_nombre = etiqueta_nombre
        etiqueta.parent_id = parent_id
        etiqueta.save()
    else:
        etiqueta = Etiqueta.objects.create(etiqueta_nombre=etiqueta_nombre, parent_id=parent_id)

    EtiquetaRol.objects.filter(etiqueta=etiqueta).delete()
    EtiquetaRol.objects.bulk_create([EtiquetaRol(etiqueta=etiqueta, rol_id=rol_id) for rol_id in set(roles_permitidos)])
    invalidar('etiquetas')
    return etiqueta


@transaction.atomic
def eliminar_etiqueta(etiqueta_id: int) -> None:
    etiqueta = Etiqueta.objects.get(pk=etiqueta_id)
    if Etiqueta.objects.filter(parent_id=etiqueta_id).exists():
        raise ValidationError('No se puede eliminar: tiene etiquetas hijas. Elimínalas o muévelas primero.')
    if DocsEtiqueta.objects.filter(etiqueta_id=etiqueta_id).exists():
        raise ValidationError('No se puede eliminar: tiene documentos asociados.')

    EtiquetaRol.objects.filter(etiqueta_id=etiqueta_id).delete()
    etiqueta.delete()
    invalidar('etiquetas')
