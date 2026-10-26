from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from apps.documentos.models import Etiqueta, EtiquetaRol
from apps.usuarios.models import Usuario

from . import storage
from .models import Actividad, Comunicado, Imagen


def crear_imagen_carrusel(archivo: UploadedFile) -> Imagen:
    ruta = storage.guardar_imagen_carrusel(archivo)
    return Imagen.objects.create(archivo=archivo.name, ruta_img=ruta, puesto=1, creado_en=timezone.now())


def actualizar_puesto_imagen(imagen_id: int, puesto: int) -> Imagen:
    imagen = Imagen.objects.get(pk=imagen_id)
    imagen.puesto = puesto
    imagen.save(update_fields=['puesto'])
    return imagen


def eliminar_imagen(imagen_id: int) -> None:
    Imagen.objects.filter(pk=imagen_id).delete()


def guardar_comunicado(
    usuario: Usuario,
    comunicado_id: int | None,
    titulo: str,
    contenido: str,
    archivo: UploadedFile | None,
) -> Comunicado:
    if comunicado_id:
        comunicado = Comunicado.objects.get(pk=comunicado_id)
        comunicado.titulo = titulo
        comunicado.contenido = contenido
        if archivo is not None:
            comunicado.imagen = storage.guardar_imagen_comunicado(archivo)
        comunicado.save()
        return comunicado

    if archivo is None:
        raise ValueError('Se requiere una imagen para publicar un comunicado nuevo.')

    return Comunicado.objects.create(
        titulo=titulo,
        contenido=contenido,
        imagen=storage.guardar_imagen_comunicado(archivo),
        usuario_sube=usuario.email,
        fecha_subida=timezone.localdate(),
    )


def eliminar_comunicado(comunicado_id: int) -> None:
    Comunicado.objects.filter(pk=comunicado_id).delete()


def crear_actividad(fecha, titulo: str, descripcion: str, hora_desde, hora_hasta) -> Actividad:
    return Actividad.objects.create(
        fecha=fecha, titulo=titulo, descripcion=descripcion, hora_desde=hora_desde, hora_hasta=hora_hasta
    )


def guardar_etiqueta(etiqueta_id: int | None, etiqueta_nombre: str, parent_id: int | None, roles_permitidos: list[int]) -> Etiqueta:
    if etiqueta_id:
        etiqueta = Etiqueta.objects.get(pk=etiqueta_id)
        etiqueta.etiqueta_nombre = etiqueta_nombre
        etiqueta.parent_id = parent_id
        etiqueta.save()
    else:
        etiqueta = Etiqueta.objects.create(etiqueta_nombre=etiqueta_nombre, parent_id=parent_id)

    EtiquetaRol.objects.filter(etiqueta=etiqueta).delete()
    EtiquetaRol.objects.bulk_create([EtiquetaRol(etiqueta=etiqueta, rol_id=rol_id) for rol_id in roles_permitidos])
    return etiqueta


def eliminar_etiqueta(etiqueta_id: int) -> None:
    EtiquetaRol.objects.filter(etiqueta_id=etiqueta_id).delete()
    Etiqueta.objects.filter(pk=etiqueta_id).delete()
