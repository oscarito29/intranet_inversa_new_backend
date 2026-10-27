from django.db.models import Q, QuerySet

from apps.core.permissions import ROL_ADMIN
from apps.usuarios.models import Usuario

from .models import Category, DocsEtiqueta, Etiqueta, EtiquetaRol, Upload


def listar_categorias():
    return Category.objects.order_by('name')


def listar_etiquetas():
    return Etiqueta.objects.order_by('etiqueta_nombre')


def listar_documentos(usuario: Usuario) -> QuerySet[Upload]:
    """
    El admin ve todo. El resto ve los documentos con al menos una etiqueta permitida para
    su rol (`etiqueta_rol`) y los que no tienen etiquetas.
    """
    consulta = Upload.objects.select_related('area').order_by('-fecha')
    if usuario.rol_id == ROL_ADMIN:
        return consulta

    con_etiquetas = DocsEtiqueta.objects.values('documento_id')
    etiquetas_permitidas = EtiquetaRol.objects.filter(rol_id=usuario.rol_id).values('etiqueta_id')
    con_etiqueta_permitida = DocsEtiqueta.objects.filter(etiqueta_id__in=etiquetas_permitidas).values('documento_id')
    return consulta.filter(Q(pk__in=con_etiqueta_permitida) | ~Q(pk__in=con_etiquetas))


def listar_docs_etiquetas(usuario: Usuario) -> dict[int, list[int]]:
    """Forma exacta que espera el frontend: {documento_id: [etiqueta_id, ...]}, solo de los documentos visibles."""
    visibles = listar_documentos(usuario).values('pk')
    resultado: dict[int, list[int]] = {}
    for fila in DocsEtiqueta.objects.filter(documento_id__in=visibles).values('documento_id', 'etiqueta_id'):
        resultado.setdefault(fila['documento_id'], []).append(fila['etiqueta_id'])
    return resultado


def categoria_tiene_documentos(category_id: int) -> bool:
    """`upload.area` tiene clave foránea real: con cualquier documento, vigente o reemplazado, no se puede borrar."""
    return Upload.objects.filter(area_id=category_id).exists()
