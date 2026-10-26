from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.financial.models import Bitacora
from apps.usuarios.models import Usuario

from . import selectors
from .models import Category, Upload
from .storage import guardar_documento_institucional, tamanio_legible


def _registrar_bitacora(usuario_email: str, accion: str, descripcion: str) -> None:
    Bitacora.objects.create(usuario=usuario_email, accion=accion, descripcion=descripcion[:100], fecha=timezone.now())


def _requerir_admin(usuario: Usuario) -> None:
    if usuario.rol_id != 1:
        raise PermissionDenied('Solo un administrador puede realizar esta acción.')


def crear_categoria(usuario: Usuario, name: str, description: str) -> Category:
    _requerir_admin(usuario)
    if Category.objects.filter(name__iexact=name).exists():
        raise ValidationError('Ya existe una categoría con ese nombre.')
    categoria = Category.objects.create(name=name, description=description, created_at=timezone.now(), estado='Activo')
    _registrar_bitacora(usuario.email, 'Creacion', f'Creacion de la categoria {name}')
    return categoria


def actualizar_categoria(usuario: Usuario, category_id: int, name: str, description: str) -> Category:
    _requerir_admin(usuario)
    if Category.objects.filter(name__iexact=name).exclude(pk=category_id).exists():
        raise ValidationError('Ya existe una categoría con ese nombre.')
    categoria = Category.objects.get(pk=category_id)
    categoria.name = name
    categoria.description = description
    categoria.modified_at = timezone.now()
    categoria.save(update_fields=['name', 'description', 'modified_at'])
    _registrar_bitacora(usuario.email, 'Edicion', f'Modificacion de la categoria {name}')
    return categoria


def eliminar_categoria(usuario: Usuario, category_id: int) -> None:
    _requerir_admin(usuario)
    selectors.validar_categoria_eliminable(category_id)
    categoria = Category.objects.get(pk=category_id)
    nombre = categoria.name
    categoria.delete()
    _registrar_bitacora(usuario.email, 'Eliminacion', f'Eliminacion de la categoria {nombre}')


def subir_documento(usuario: Usuario, archivo, name: str, area_id: int, tag_ids: list[int]) -> Upload:
    ruta = guardar_documento_institucional(archivo, area_id)
    documento = Upload.objects.create(
        reemplaza_a=None,
        fname=ruta,
        name=name,
        area_id=area_id,
        estado='Activo',
        fecha=timezone.now(),
        tipo=archivo.content_type or 'application/octet-stream',
        tamanio=tamanio_legible(archivo.size),
    )
    if tag_ids:
        from .models import DocsEtiqueta

        DocsEtiqueta.objects.bulk_create([DocsEtiqueta(documento=documento, etiqueta_id=tag_id) for tag_id in tag_ids])
    _registrar_bitacora(usuario.email, 'Creacion', f'Sube el documento {name}')
    return documento


def reemplazar_documento(usuario: Usuario, replaces_id: int, archivo, name: str, area_id: int, tag_ids: list[int]) -> Upload:
    _requerir_admin(usuario)
    original = Upload.objects.get(pk=replaces_id)

    nuevo = subir_documento(usuario, archivo, name, area_id, tag_ids)
    nuevo.reemplaza_a_id = replaces_id
    nuevo.save(update_fields=['reemplaza_a'])

    original.estado = 'Reemplazado'
    original.save(update_fields=['estado'])

    _registrar_bitacora(usuario.email, 'Edicion', f'Reemplaza el documento {original.name}')
    return nuevo
