from django.core.exceptions import ValidationError

from .models import Category, DocsEtiqueta, Etiqueta, Upload


def listar_categorias():
    return Category.objects.order_by('name')


def listar_etiquetas():
    return Etiqueta.objects.order_by('etiqueta_nombre')


def listar_documentos():
    return Upload.objects.select_related('area').order_by('-fecha')


def listar_docs_etiquetas() -> dict[int, list[int]]:
    """Forma exacta que espera el frontend: {documento_id: [etiqueta_id, ...]}."""
    resultado: dict[int, list[int]] = {}
    for fila in DocsEtiqueta.objects.all().values('documento_id', 'etiqueta_id'):
        resultado.setdefault(fila['documento_id'], []).append(fila['etiqueta_id'])
    return resultado


def validar_categoria_eliminable(category_id: int) -> None:
    if Upload.objects.filter(area_id=category_id, estado='Activo').exists():
        raise ValidationError('No se puede eliminar: tiene documentos asociados.')
