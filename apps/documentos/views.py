from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import cached
from apps.core.permissions import AdminParaEscritura, EsAdministrador

from . import selectors, services
from .serializers import (
    CategorySerializer,
    CategoryWriteSerializer,
    DocumentoSubidaSerializer,
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
        return Response(CategorySerializer(categoria).data, status=status.HTTP_201_CREATED)


class CategoriaDetailView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Actualizar categoría', tags=[TAG], request=CategoryWriteSerializer, responses=CategorySerializer)
    def put(self, request: Request, category_id: int) -> Response:
        serializer = CategoryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        categoria = services.actualizar_categoria(request.user, category_id, **serializer.validated_data)
        return Response(CategorySerializer(categoria).data)

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


class DocumentosView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AdminParaEscritura]

    @extend_schema(
        summary='Listar documentos institucionales visibles para el rol del usuario',
        tags=[TAG],
        responses=DocumentSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        return Response(DocumentSerializer(selectors.listar_documentos(request.user), many=True).data)

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
