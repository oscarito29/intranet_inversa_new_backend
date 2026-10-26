from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied as DrfPermissionDenied
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import selectors, services
from .models import Category, Upload
from .serializers import CategorySerializer, CategoryWriteSerializer, DocumentSerializer, TagSerializer


def _reraise_como_drf(exc: Exception):
    if isinstance(exc, PermissionDenied):
        raise DrfPermissionDenied(str(exc)) from exc
    if isinstance(exc, DjangoValidationError):
        raise DrfValidationError(str(exc)) from exc
    raise exc


class CategoriasView(APIView):
    @extend_schema(summary='Listar categorías')
    def get(self, request: Request) -> Response:
        return Response(CategorySerializer(selectors.listar_categorias(), many=True).data)

    @extend_schema(summary='Crear categoría', request=CategoryWriteSerializer)
    def post(self, request: Request) -> Response:
        serializer = CategoryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            categoria = services.crear_categoria(request.user, **serializer.validated_data)
        except (PermissionDenied, DjangoValidationError) as exc:
            _reraise_como_drf(exc)
        return Response(CategorySerializer(categoria).data, status=status.HTTP_201_CREATED)


class CategoriaDetailView(APIView):
    @extend_schema(summary='Actualizar categoría', request=CategoryWriteSerializer)
    def put(self, request: Request, category_id: int) -> Response:
        serializer = CategoryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            categoria = services.actualizar_categoria(request.user, category_id, **serializer.validated_data)
        except (PermissionDenied, DjangoValidationError) as exc:
            _reraise_como_drf(exc)
        except Category.DoesNotExist:
            raise DrfValidationError({'detail': 'La categoría no existe.'})
        return Response(CategorySerializer(categoria).data)

    @extend_schema(summary='Eliminar categoría')
    def delete(self, request: Request, category_id: int) -> Response:
        try:
            services.eliminar_categoria(request.user, category_id)
        except (PermissionDenied, DjangoValidationError) as exc:
            _reraise_como_drf(exc)
        except Category.DoesNotExist:
            raise DrfValidationError({'detail': 'La categoría no existe.'})
        return Response(status=status.HTTP_204_NO_CONTENT)


class EtiquetasListView(APIView):
    @extend_schema(summary='Listar etiquetas (solo lectura, para filtros de documentos)')
    def get(self, request: Request) -> Response:
        return Response(TagSerializer(selectors.listar_etiquetas(), many=True).data)


class DocsEtiquetasView(APIView):
    @extend_schema(summary='Mapa documento_id -> [etiqueta_id, ...]')
    def get(self, request: Request) -> Response:
        return Response(selectors.listar_docs_etiquetas())


def _parse_tag_ids(request: Request) -> list[int]:
    valores = request.data.getlist('tagIds') if hasattr(request.data, 'getlist') else request.data.get('tagIds', [])
    return [int(v) for v in valores if str(v).strip()]


class DocumentosView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary='Listar documentos institucionales')
    def get(self, request: Request) -> Response:
        return Response(DocumentSerializer(selectors.listar_documentos(), many=True).data)

    @extend_schema(summary='Subir un documento institucional nuevo')
    def post(self, request: Request) -> Response:
        archivo = request.FILES.get('file')
        if archivo is None:
            raise DrfValidationError({'file': 'Este campo es requerido.'})
        try:
            documento = services.subir_documento(
                usuario=request.user,
                archivo=archivo,
                name=request.data.get('name'),
                area_id=request.data.get('area'),
                tag_ids=_parse_tag_ids(request),
            )
        except DjangoValidationError as exc:
            _reraise_como_drf(exc)
        return Response(DocumentSerializer(documento).data, status=status.HTTP_201_CREATED)


class DocumentoReemplazarView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary='Reemplazar (versionar) un documento institucional — solo Admin')
    def post(self, request: Request, documento_id: int) -> Response:
        archivo = request.FILES.get('file')
        if archivo is None:
            raise DrfValidationError({'file': 'Este campo es requerido.'})
        try:
            documento = services.reemplazar_documento(
                usuario=request.user,
                replaces_id=documento_id,
                archivo=archivo,
                name=request.data.get('name'),
                area_id=request.data.get('area'),
                tag_ids=_parse_tag_ids(request),
            )
        except (PermissionDenied, DjangoValidationError) as exc:
            _reraise_como_drf(exc)
        except Upload.DoesNotExist:
            raise DrfValidationError({'detail': 'El documento original no existe.'})
        return Response(DocumentSerializer(documento).data, status=status.HTTP_201_CREATED)
