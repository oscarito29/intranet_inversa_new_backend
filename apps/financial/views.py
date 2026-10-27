from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import cached
from apps.core.exportacion import TIPO_XLSX, generar_xlsx, respuesta_xlsx
from apps.core.permissions import Permiso, permisos_de, requiere
from apps.usuarios.alcance import entidades_de

from . import selectors, services
from .serializers import (
    AnioSerializer,
    CorporacionSerializer,
    DocumentoSerializer,
    DocumentosQuerySerializer,
    HistorialEventoSerializer,
    MesSerializer,
    NotificacionesSerializer,
    PeriodoFilaSerializer,
    PeriodoQuerySerializer,
    RangoFechasRequestSerializer,
    RechazarRevocarRequestSerializer,
    SubirDocumentoSerializer,
)

TAG = 'Financiero'
TTL_CATALOGOS = 60 * 5


def _catalogos_globales() -> dict:
    """Parte de los catálogos que es igual para todos los usuarios (la única que se cachea)."""
    rango = selectors.obtener_rango_vigente()
    return {
        'anios': list(AnioSerializer(selectors.listar_anios(), many=True).data),
        'meses': list(MesSerializer(selectors.listar_meses(), many=True).data),
        'corporaciones': list(CorporacionSerializer(selectors.listar_corporaciones_con_financieras(), many=True).data),
        'rango_vigente': {'desde': rango.desde, 'hasta': rango.hasta} if rango else None,
    }


class CatalogosView(APIView):
    @extend_schema(
        summary='Catálogos del módulo financiero',
        description='Años, meses, corporaciones con sus financieras, rango de fechas vigente y el acceso del usuario: sus permisos y las entidades que puede ver.',
        tags=[TAG],
    )
    def get(self, request: Request) -> Response:
        usuario = request.user
        return Response(
            {
                **cached('financiero:catalogos', TTL_CATALOGOS, _catalogos_globales),
                'notificaciones_pendientes': selectors.contar_pendientes(usuario),
                'usuario_acceso': {
                    'rol_id': usuario.rol_id,
                    'permisos': permisos_de(usuario),
                    'financiera_id': usuario.financiera_id,
                    # Su entidad principal y las adicionales. Con `financiero.ver_todas` no se limita por ellas.
                    'financiera_ids': sorted(entidades_de(usuario)),
                },
            }
        )


class ResumenView(APIView):
    @extend_schema(
        summary='Resumen de documentos para el dashboard',
        description='Pendientes de aprobar, rechazados del mes y documentos nuevos de la semana, según el alcance del usuario.',
        tags=[TAG],
    )
    def get(self, request: Request) -> Response:
        return Response(selectors.obtener_resumen(request.user))


class NotificacionesView(APIView):
    @extend_schema(
        summary='Notificaciones de la campana',
        description='Quien puede aprobar: documentos pendientes de aprobar. Quien sube: documentos de sus entidades rechazados o '
        'revocados en los últimos 30 días. Quien solo consulta: sin avisos. `total` los cuenta todos; `items` trae los 20 más recientes.',
        tags=[TAG],
        responses=NotificacionesSerializer,
    )
    def get(self, request: Request) -> Response:
        return Response(NotificacionesSerializer(selectors.obtener_notificaciones(request.user)).data)


class PeriodoView(APIView):
    @extend_schema(
        summary='Estado de cada financiera de una corporación en un periodo',
        description='Resumen (cargadas, faltan, por estado) y una fila por financiera con su documento más reciente. '
        'Quien puede ver todas las entidades ve todas las financieras; el resto, solo las suyas.',
        tags=[TAG],
        parameters=[
            OpenApiParameter('anio', int, required=True),
            OpenApiParameter('mes', int, required=True),
            OpenApiParameter('corporacion', str, required=True),
        ],
    )
    def get(self, request: Request) -> Response:
        parametros = PeriodoQuerySerializer(data=request.query_params)
        parametros.is_valid(raise_exception=True)
        datos = parametros.validated_data
        periodo = selectors.obtener_periodo(request.user, datos['anio'], datos['mes'], datos['corporacion'])
        return Response({'resumen': periodo['resumen'], 'financieras': PeriodoFilaSerializer(periodo['filas'], many=True).data})


class ExportarPeriodoView(APIView):
    permission_classes = [requiere(Permiso.FINANCIERO_EXPORTAR)]

    @extend_schema(
        summary='Exportar a Excel el estado de cada financiera en un periodo',
        description='Mismas filas que `GET /financiero/periodo/`. Requiere el permiso de exportar (administrador, aprobador y consulta).',
        tags=[TAG],
        parameters=[
            OpenApiParameter('anio', int, required=True),
            OpenApiParameter('mes', int, required=True),
            OpenApiParameter('corporacion', str, required=True),
        ],
        responses={(200, TIPO_XLSX): OpenApiTypes.BINARY},
    )
    def get(self, request: Request) -> HttpResponse:
        parametros = PeriodoQuerySerializer(data=request.query_params)
        parametros.is_valid(raise_exception=True)
        datos = parametros.validated_data
        filas = selectors.filas_de_exportacion_del_periodo(request.user, datos['anio'], datos['mes'], datos['corporacion'])
        anio_numero = selectors.obtener_numero_de_anio(datos['anio'])
        services.registrar_exportacion_del_periodo(request.user, anio_numero, datos['mes'], datos['corporacion'])
        nombre = f"estados-financieros-{anio_numero}-{datos['mes']:02d}-corporacion-{datos['corporacion']}.xlsx"
        return respuesta_xlsx(nombre, generar_xlsx('Periodo', selectors.ENCABEZADOS_DE_EXPORTACION, filas))


class DocumentosView(APIView):
    permission_classes = [requiere(Permiso.FINANCIERO_SUBIR, solo_escritura=True)]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary='Listar documentos de una financiera/periodo',
        tags=[TAG],
        parameters=[
            OpenApiParameter('anio', int, required=True),
            OpenApiParameter('mes', int, required=True),
            OpenApiParameter('corporacion', str, required=True),
            OpenApiParameter('financiera', str, required=True),
        ],
        responses=DocumentoSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        parametros = DocumentosQuerySerializer(data=request.query_params)
        parametros.is_valid(raise_exception=True)
        datos = parametros.validated_data
        documentos = selectors.obtener_documentos(
            usuario=request.user,
            anio=datos['anio'],
            mes_id=datos['mes'],
            corporacion_id=datos['corporacion'],
            financiera_id=datos['financiera'],
        )
        return Response(DocumentoSerializer(documentos, many=True).data)

    @extend_schema(summary='Subir un documento financiero', tags=[TAG], request=SubirDocumentoSerializer, responses={201: DocumentoSerializer})
    def post(self, request: Request) -> Response:
        entrada = SubirDocumentoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        documento = services.subir_documento(
            usuario=request.user,
            archivo=datos['file'],
            anio=datos['anio'],
            mes_id=datos['mes_id'],
            corporacion_id=datos['corporacion_id'],
            financiera_id=datos['financiera_id'],
        )
        return Response(DocumentoSerializer(documento).data, status=status.HTTP_201_CREATED)


class DocumentoHistorialView(APIView):
    @extend_schema(summary='Historial de un documento: quién lo subió, aprobó, rechazó o revocó, y cuándo', tags=[TAG], responses=HistorialEventoSerializer(many=True))
    def get(self, request: Request, documento_id: int) -> Response:
        return Response(HistorialEventoSerializer(selectors.obtener_historial(request.user, documento_id), many=True).data)


class DocumentoAprobarView(APIView):
    permission_classes = [requiere(Permiso.FINANCIERO_APROBAR)]

    @extend_schema(summary='Aprobar un estado financiero', tags=[TAG], request=None, responses=DocumentoSerializer)
    def post(self, request: Request, documento_id: int) -> Response:
        documento = services.aprobar_documento(request.user, documento_id)
        return Response(DocumentoSerializer(documento).data)


class DocumentoRechazarView(APIView):
    permission_classes = [requiere(Permiso.FINANCIERO_APROBAR)]

    @extend_schema(
        summary='Rechazar un estado financiero',
        tags=[TAG],
        request=RechazarRevocarRequestSerializer,
        responses=DocumentoSerializer,
    )
    def post(self, request: Request, documento_id: int) -> Response:
        serializer = RechazarRevocarRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documento = services.rechazar_documento(request.user, documento_id, serializer.validated_data['motivo'])
        return Response(DocumentoSerializer(documento).data)


class DocumentoRevocarView(APIView):
    permission_classes = [requiere(Permiso.FINANCIERO_APROBAR)]

    @extend_schema(
        summary='Revocar un estado financiero aprobado o rechazado',
        tags=[TAG],
        request=RechazarRevocarRequestSerializer,
        responses=DocumentoSerializer,
    )
    def post(self, request: Request, documento_id: int) -> Response:
        serializer = RechazarRevocarRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documento = services.revocar_documento(request.user, documento_id, serializer.validated_data['motivo'])
        return Response(DocumentoSerializer(documento).data)


class RangoFechasView(APIView):
    permission_classes = [requiere(Permiso.FINANCIERO_RANGO_FECHAS)]

    @extend_schema(
        summary='Fijar el rango de fechas vigente para subir documentos',
        tags=[TAG],
        request=RangoFechasRequestSerializer,
        responses={201: RangoFechasRequestSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = RangoFechasRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rango = services.guardar_rango_fechas(request.user, serializer.validated_data['desde'], serializer.validated_data['hasta'])
        return Response({'desde': rango.desde, 'hasta': rango.hasta}, status=status.HTTP_201_CREATED)
