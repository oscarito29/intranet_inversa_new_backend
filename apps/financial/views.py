from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied as DrfPermissionDenied
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import selectors, services
from .models import Documento
from .permissions import EsAdministrador
from .serializers import (
    AnioSerializer,
    CorporacionSerializer,
    DocumentoSerializer,
    MesSerializer,
    RangoFechasRequestSerializer,
    RechazarRevocarRequestSerializer,
)


def _reraise_como_drf(exc: Exception):
    if isinstance(exc, PermissionDenied):
        raise DrfPermissionDenied(str(exc)) from exc
    if isinstance(exc, DjangoValidationError):
        raise DrfValidationError(str(exc)) from exc
    raise exc


class CatalogosView(APIView):
    @extend_schema(
        summary='Catálogos del módulo financiero',
        description='Años, meses, corporaciones con sus financieras, rango de fechas vigente y nivel de acceso del usuario.',
    )
    def get(self, request: Request) -> Response:
        usuario = request.user
        rango = selectors.obtener_rango_vigente()

        return Response(
            {
                'anios': AnioSerializer(selectors.listar_anios(), many=True).data,
                'meses': MesSerializer(selectors.listar_meses(), many=True).data,
                'corporaciones': CorporacionSerializer(selectors.listar_corporaciones_con_financieras(), many=True).data,
                'rango_vigente': {'desde': rango.desde, 'hasta': rango.hasta} if rango else None,
                'notificaciones_pendientes': selectors.contar_notificaciones_pendientes(usuario),
                'usuario_acceso': {
                    'rol_id': usuario.rol_id,
                    'es_admin': usuario.rol_id == 1,
                    'financiera_id': usuario.financiera_id,
                },
            }
        )


class ResumenView(APIView):
    @extend_schema(
        summary='Resumen de documentos para el dashboard',
        description='Pendientes de aprobar, rechazados del mes y documentos nuevos de la semana, según el alcance del usuario.',
    )
    def get(self, request: Request) -> Response:
        return Response(selectors.obtener_resumen(request.user))


class DocumentosView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary='Listar documentos de una financiera/periodo',
        parameters=[
            OpenApiParameter('anio', int, required=True),
            OpenApiParameter('mes', int, required=True),
            OpenApiParameter('corporacion', str, required=True),
            OpenApiParameter('financiera', str, required=True),
        ],
    )
    def get(self, request: Request) -> Response:
        try:
            documentos = selectors.obtener_documentos(
                usuario=request.user,
                anio=request.query_params.get('anio'),
                mes_id=request.query_params.get('mes'),
                corporacion_id=request.query_params.get('corporacion'),
                financiera_id=request.query_params.get('financiera'),
            )
        except PermissionDenied as exc:
            _reraise_como_drf(exc)
        return Response(DocumentoSerializer(documentos, many=True).data)

    @extend_schema(summary='Subir un documento financiero')
    def post(self, request: Request) -> Response:
        archivo = request.FILES.get('file')
        if archivo is None:
            raise DrfValidationError({'file': 'Este campo es requerido.'})

        try:
            documento = services.subir_documento(
                usuario=request.user,
                archivo=archivo,
                anio=request.data.get('anio'),
                mes_id=request.data.get('mes_id'),
                corporacion_id=request.data.get('corporacion_id'),
                financiera_id=request.data.get('financiera_id'),
            )
        except (PermissionDenied, DjangoValidationError) as exc:
            _reraise_como_drf(exc)
        return Response(DocumentoSerializer(documento).data, status=status.HTTP_201_CREATED)


class DocumentoAprobarView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Aprobar un estado financiero')
    def post(self, request: Request, documento_id: int) -> Response:
        try:
            documento = services.aprobar_documento(request.user, documento_id)
        except Documento.DoesNotExist:
            raise DrfValidationError({'detail': 'El documento no existe.'})
        return Response(DocumentoSerializer(documento).data)


class DocumentoRechazarView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Rechazar un estado financiero', request=RechazarRevocarRequestSerializer)
    def post(self, request: Request, documento_id: int) -> Response:
        serializer = RechazarRevocarRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            documento = services.rechazar_documento(request.user, documento_id, serializer.validated_data['motivo'])
        except Documento.DoesNotExist:
            raise DrfValidationError({'detail': 'El documento no existe.'})
        return Response(DocumentoSerializer(documento).data)


class DocumentoRevocarView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Revocar un estado financiero ya aprobado', request=RechazarRevocarRequestSerializer)
    def post(self, request: Request, documento_id: int) -> Response:
        serializer = RechazarRevocarRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            documento = services.revocar_documento(request.user, documento_id, serializer.validated_data['motivo'])
        except Documento.DoesNotExist:
            raise DrfValidationError({'detail': 'El documento no existe.'})
        return Response(DocumentoSerializer(documento).data)


class RangoFechasView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Fijar el rango de fechas vigente para subir documentos', request=RangoFechasRequestSerializer)
    def post(self, request: Request) -> Response:
        serializer = RangoFechasRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rango = services.guardar_rango_fechas(
            request.user, serializer.validated_data['desde'], serializer.validated_data['hasta']
        )
        return Response({'desde': rango.desde, 'hasta': rango.hasta}, status=status.HTTP_201_CREATED)
