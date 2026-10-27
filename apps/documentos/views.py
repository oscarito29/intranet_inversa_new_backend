from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import cached
from apps.core.exportacion import TIPO_XLSX, generar_xlsx, respuesta_xlsx
from apps.core.permissions import AdminParaEscritura, EsAdministrador

from . import selectors, services
from .serializers import (
    CategoryEstadoSerializer,
    CategorySerializer,
    CategoryWriteSerializer,
    DocumentoListaSerializer,
    DocumentoSubidaSerializer,
    DocumentosConsultaSerializer,
    DocumentSerializer,
    TagSerializer,
)

TAG = 'Documentos'
TTL_CATALOGOS = 60 * 5


class CategoriasView(APIView):
    permission_classes = [AdminParaEscritura]

    @extend_schema(summary='Listar categorías', tags=[TAG], responses=CategorySerializer(many=True))
    def get(self, request: Request) -> Response:
        datos = cached(
            'documentos:categorias',
            TTL_CATALOGOS,
            lambda: list(CategorySerializer(selectors.listar_categorias(), many=True).data),
        )
        return Response(datos)

    @extend_schema(summary='Crear categoría', tags=[TAG], request=CategoryWriteSerializer, responses={201: CategorySerializer})
    def post(self, request: Request) -> Response:
        serializer = CategoryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        categoria = services.crear_categoria(request.user, **serializer.validated_data)
        return Response(CategorySerializer(selectors.obtener_categoria(categoria.id)).data, status=status.HTTP_201_CREATED)


class CategoriaDetailView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Actualizar categoría', tags=[TAG], request=CategoryWriteSerializer, responses=CategorySerializer)
    def put(self, request: Request, category_id: int) -> Response:
        serializer = CategoryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        categoria = services.actualizar_categoria(request.user, category_id, **serializer.validated_data)
        return Response(CategorySerializer(selectors.obtener_categoria(categoria.id)).data)

    @extend_schema(
        summary='Activar o desactivar una categoría',
        description='Una categoría inactiva conserva sus documentos pero no admite subir otros nuevos.',
        tags=[TAG],
        request=CategoryEstadoSerializer,
        responses=CategorySerializer,
    )
    def patch(self, request: Request, category_id: int) -> Response:
        serializer = CategoryEstadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        categoria = services.cambiar_estado_categoria(request.user, category_id, serializer.validated_data['estado'])
        return Response(CategorySerializer(selectors.obtener_categoria(categoria.id)).data)

    @extend_schema(summary='Eliminar categoría', tags=[TAG], responses={204: None})
    def delete(self, request: Request, category_id: int) -> Response:
        services.eliminar_categoria(request.user, category_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EtiquetasListView(APIView):
    @extend_schema(summary='Listar etiquetas (solo lectura, para filtros de documentos)', tags=[TAG], responses=TagSerializer(many=True))
    def get(self, request: Request) -> Response:
        datos = cached(
            'etiquetas:por-nombre',
            TTL_CATALOGOS,
            lambda: list(TagSerializer(selectors.listar_etiquetas(), many=True).data),
        )
        return Response(datos)


class DocsEtiquetasView(APIView):
    @extend_schema(summary='Mapa documento_id -> [etiqueta_id, ...] de los documentos visibles para el rol', tags=[TAG])
    def get(self, request: Request) -> Response:
        return Response(selectors.listar_docs_etiquetas(request.user))


class DocumentosExportarView(APIView):
    @extend_schema(
        summary='Exportar a Excel los documentos vigentes visibles para el rol',
        description='Acepta los filtros de la lista (`q`, `categoria`, `etiquetas`, `orden`) e ignora la paginación: salen todos los '
        'que coinciden, hasta 5000.',
        tags=[TAG],
        parameters=[DocumentosConsultaSerializer],
        responses={(200, TIPO_XLSX): OpenApiTypes.BINARY},
    )
    def get(self, request: Request) -> HttpResponse:
        consulta = DocumentosConsultaSerializer(data=request.query_params)
        consulta.is_valid(raise_exception=True)
        filtros = consulta.validated_data
        filas = selectors.filas_de_exportacion_de_documentos(
            request.user,
            texto=filtros['q'].strip(),
            categoria_id=filtros['categoria'],
            etiqueta_ids=filtros['etiquetas'],
            orden=filtros['orden'],
        )
        return respuesta_xlsx('documentos.xlsx', generar_xlsx('Documentos', selectors.ENCABEZADOS_DE_EXPORTACION, filas))


class DocumentosView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AdminParaEscritura]

    @extend_schema(
        summary='Listar, paginados, los documentos vigentes visibles para el rol del usuario',
        description='Filtra por texto (`q`), categoría (`categoria`) y etiquetas (`etiquetas=1,2`, el documento debe tenerlas todas). '
        'Cada fila trae sus etiquetas, si su archivo está disponible y las versiones que reemplazó; `categorias` cuenta '
        'los vigentes por categoría sin aplicar el filtro de categoría.',
        tags=[TAG],
        parameters=[DocumentosConsultaSerializer],
    )
    def get(self, request: Request) -> Response:
        consulta = DocumentosConsultaSerializer(data=request.query_params)
        consulta.is_valid(raise_exception=True)
        filtros = consulta.validated_data
        pagina = selectors.obtener_pagina_de_documentos(
            request.user,
            texto=filtros['q'].strip(),
            categoria_id=filtros['categoria'],
            etiqueta_ids=filtros['etiquetas'],
            pagina=filtros['page'],
            tamanio=filtros['page_size'],
            orden=filtros['orden'],
        )
        contexto = {'etiquetas': pagina['etiquetas'], 'versiones': pagina['versiones']}
        return Response(
            {
                'count': pagina['total'],
                'page': pagina['pagina'],
                'page_size': pagina['tamanio'],
                'total_pages': pagina['paginas'],
                'categorias': pagina['categorias'],
                'results': DocumentoListaSerializer(pagina['documentos'], many=True, context=contexto).data,
            }
        )

    @extend_schema(
        summary='Subir un documento institucional nuevo (solo Admin)',
        tags=[TAG],
        request=DocumentoSubidaSerializer,
        responses={201: DocumentSerializer},
    )
    def post(self, request: Request) -> Response:
        entrada = DocumentoSubidaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        documento = services.subir_documento(
            usuario=request.user,
            archivo=datos['file'],
            name=datos['name'],
            area_id=datos['area'],
            tag_ids=datos['tagIds'],
        )
        return Response(DocumentSerializer(documento).data, status=status.HTTP_201_CREATED)


class DocumentoReemplazarView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [EsAdministrador]

    @extend_schema(
        summary='Reemplazar (versionar) un documento institucional — solo Admin',
        tags=[TAG],
        request=DocumentoSubidaSerializer,
        responses={201: DocumentSerializer},
    )
    def post(self, request: Request, documento_id: int) -> Response:
        entrada = DocumentoSubidaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        documento = services.reemplazar_documento(
            usuario=request.user,
            replaces_id=documento_id,
            archivo=datos['file'],
            name=datos['name'],
            area_id=datos['area'],
            tag_ids=datos['tagIds'],
        )
        return Response(DocumentSerializer(documento).data, status=status.HTTP_201_CREATED)
