from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.bitacora import registrar_bitacora
from apps.core.cache import invalidar
from apps.usuarios.models import Usuario

from . import selectors
from .models import Category, DocsEtiqueta, Upload
from .storage import guardar_documento_institucional, tamanio_legible


@transaction.atomic
def crear_categoria(usuario: Usuario, name: str, description: str) -> Category:
    if Category.objects.filter(name__iexact=name).exists():
        raise ValidationError({'name': 'Ya existe una categoría con ese nombre.'})
    categoria = Category.objects.create(name=name, description=description, created_at=timezone.now(), estado=Category.ACTIVA)
    registrar_bitacora(usuario.email, 'Creacion', f'Creacion de la categoria {name}')
    invalidar('documentos')
    return categoria


@transaction.atomic
def actualizar_categoria(usuario: Usuario, category_id: int, name: str, description: str) -> Category:
    categoria = Category.objects.get(pk=category_id)
    if Category.objects.filter(name__iexact=name).exclude(pk=category_id).exists():
        raise ValidationError({'name': 'Ya existe una categoría con ese nombre.'})
    categoria.name = name
    categoria.description = description
    categoria.modified_at = timezone.now()
    categoria.save(update_fields=['name', 'description', 'modified_at'])
    registrar_bitacora(usuario.email, 'Edicion', f'Modificacion de la categoria {name}')
    invalidar('documentos')
    return categoria


@transaction.atomic
def cambiar_estado_categoria(usuario: Usuario, category_id: int, estado: str) -> Category:
    categoria = Category.objects.select_for_update().get(pk=category_id)
    if categoria.estado == estado:
        return categoria
    categoria.estado = estado
    categoria.modified_at = timezone.now()
    categoria.save(update_fields=['estado', 'modified_at'])
    accion = 'Activa' if estado == Category.ACTIVA else 'Desactiva'
    registrar_bitacora(usuario.email, 'Edicion', f'{accion} la categoria {categoria.name}')
    invalidar('documentos')
    return categoria


@transaction.atomic
def eliminar_categoria(usuario: Usuario, category_id: int) -> None:
    categoria = Category.objects.get(pk=category_id)
    if selectors.categoria_tiene_documentos(category_id):
        raise ValidationError('No se puede eliminar: tiene documentos asociados.')
    nombre = categoria.name
    categoria.delete()
    registrar_bitacora(usuario.email, 'Eliminacion', f'Eliminacion de la categoria {nombre}')
    invalidar('documentos')


@transaction.atomic
def subir_documento(usuario: Usuario, archivo, name: str, area_id: int, tag_ids: list[int]) -> Upload:
    ruta = guardar_documento_institucional(archivo, area_id)
    documento = Upload.objects.create(
        reemplaza_a=None,
        fname=ruta,
        name=name,
        area_id=area_id,
        estado=Upload.ACTIVO,
        fecha=timezone.now(),
        tipo=archivo.content_type or 'application/octet-stream',
        tamanio=tamanio_legible(archivo.size),
    )
    if tag_ids:
        DocsEtiqueta.objects.bulk_create([DocsEtiqueta(documento=documento, etiqueta_id=tag_id) for tag_id in tag_ids])
    registrar_bitacora(usuario.email, 'Creacion', f'Sube el documento {name}')
    invalidar('documentos')
    return documento


@transaction.atomic
def reemplazar_documento(usuario: Usuario, replaces_id: int, archivo, name: str, area_id: int, tag_ids: list[int]) -> Upload:
    original = Upload.objects.select_for_update().get(pk=replaces_id)
    if original.estado == Upload.REEMPLAZADO:
        raise ValidationError('Ese documento ya fue reemplazado por una versión más reciente.')

    nuevo = subir_documento(usuario, archivo, name, area_id, tag_ids)
    nuevo.reemplaza_a_id = replaces_id
    nuevo.save(update_fields=['reemplaza_a'])

    original.estado = Upload.REEMPLAZADO
    original.save(update_fields=['estado'])

    registrar_bitacora(usuario.email, 'Edicion', f'Reemplaza el documento {original.name}')
    return nuevo
