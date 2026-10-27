from django.core.paginator import Paginator
from django.db.models import Count, Q, QuerySet

from apps.core.permissions import ROL_ADMIN
from apps.usuarios.models import Usuario

from .models import Category, DocsEtiqueta, Etiqueta, EtiquetaRol, Upload


def _categorias_con_conteo() -> QuerySet[Category]:
    """`documentos`: vigentes (lo que se muestra). `documentos_totales`: incluye los reemplazados, que también impiden borrar."""
    return Category.objects.annotate(
        documentos=Count('upload', filter=~Q(upload__estado=Upload.REEMPLAZADO)),
        documentos_totales=Count('upload'),
    )


def listar_categorias() -> QuerySet[Category]:
    return _categorias_con_conteo().order_by('name')


def obtener_categoria(category_id: int) -> Category:
    return _categorias_con_conteo().get(pk=category_id)


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


TAMANIO_PAGINA_MAXIMO = 100
PROFUNDIDAD_MAXIMA_DE_VERSIONES = 50


def listar_documentos_vigentes(usuario: Usuario, texto: str = '', etiqueta_ids: tuple[int, ...] = ()) -> QuerySet[Upload]:
    """
    Documentos visibles para el rol que no han sido reemplazados, filtrados por texto y por etiquetas
    (el documento debe tenerlas todas). No filtra por categoría: así se pueden contar por categoría.
    """
    consulta = listar_documentos(usuario).exclude(estado=Upload.REEMPLAZADO)
    if texto:
        consulta = consulta.filter(name__icontains=texto)
    for etiqueta_id in etiqueta_ids:
        consulta = consulta.filter(etiquetas__etiqueta_id=etiqueta_id)
    return consulta


def contar_por_categoria(consulta: QuerySet[Upload]) -> dict[int, int]:
    filas = consulta.order_by().values('area_id').annotate(total=Count('id'))
    return {fila['area_id']: fila['total'] for fila in filas}


def etiquetas_por_documento(documento_ids: list[int]) -> dict[int, list[int]]:
    resultado: dict[int, list[int]] = {}
    for documento_id, etiqueta_id in DocsEtiqueta.objects.filter(documento_id__in=documento_ids).values_list('documento_id', 'etiqueta_id'):
        resultado.setdefault(documento_id, []).append(etiqueta_id)
    return resultado


def versiones_anteriores(documentos: list[Upload]) -> dict[int, list[Upload]]:
    """Versiones que reemplazó cada documento, de la más reciente a la más antigua (una consulta por nivel de la cadena)."""
    resultado: dict[int, list[Upload]] = {documento.id: [] for documento in documentos}
    siguiente = {documento.id: documento.reemplaza_a_id for documento in documentos if documento.reemplaza_a_id}
    vistos: dict[int, set[int]] = {documento.id: {documento.id} for documento in documentos}

    for _ in range(PROFUNDIDAD_MAXIMA_DE_VERSIONES):
        if not siguiente:
            break
        previas = {previa.id: previa for previa in Upload.objects.filter(pk__in=set(siguiente.values()))}
        proximo: dict[int, int] = {}
        for documento_id, previa_id in siguiente.items():
            previa = previas.get(previa_id)
            if previa is None or previa.id in vistos[documento_id]:
                continue
            vistos[documento_id].add(previa.id)
            resultado[documento_id].append(previa)
            if previa.reemplaza_a_id:
                proximo[documento_id] = previa.reemplaza_a_id
        siguiente = proximo
    return resultado


def obtener_pagina_de_documentos(
    usuario: Usuario,
    texto: str = '',
    categoria_id: int | None = None,
    etiqueta_ids: tuple[int, ...] = (),
    pagina: int = 1,
    tamanio: int = 20,
    orden: str = 'recientes',
) -> dict:
    """
    Una página de documentos vigentes con lo que la lista necesita: etiquetas, versiones anteriores y conteo por categoría.
    `orden` es por fecha de subida: `recientes` (por defecto) o `antiguos`; el id desempata para que las páginas no se mezclen.
    """
    sin_categoria = listar_documentos_vigentes(usuario, texto, etiqueta_ids)
    consulta = sin_categoria.filter(area_id=categoria_id) if categoria_id else sin_categoria
    consulta = consulta.order_by('fecha', 'id') if orden == 'antiguos' else consulta.order_by('-fecha', '-id')

    paginador = Paginator(consulta, min(max(tamanio, 1), TAMANIO_PAGINA_MAXIMO))
    pagina_actual = paginador.get_page(pagina)
    documentos = list(pagina_actual.object_list)

    return {
        'documentos': documentos,
        'total': paginador.count,
        'pagina': pagina_actual.number,
        'tamanio': paginador.per_page,
        'paginas': paginador.num_pages,
        'categorias': contar_por_categoria(sin_categoria),
        'etiquetas': etiquetas_por_documento([documento.id for documento in documentos]),
        'versiones': versiones_anteriores(documentos),
    }
