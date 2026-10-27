from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import cached
from apps.core.permissions import AdminParaEscritura, EsAdministrador

from . import selectors, services
from .serializers import (
    ActividadSerializer,
    ActividadWriteSerializer,
    ComunicadoSerializer,
    CumpleañoSerializer,
    EtiquetaRolSerializer,
    EtiquetaSerializer,
    ImagenSerializer,
    RolSerializer,
    SaveEtiquetaRequestSerializer,
)

TAG = 'Configuración'
TTL_CATALOGOS = 60 * 5


def _datos(serializer_class, queryset) -> list:
    return list(serializer_class(queryset, many=True).data)


class RolesView(APIView):
    @extend_schema(summary='Listar roles (solo lectura)', tags=[TAG], responses=RolSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(cached('usuarios-catalogos:roles-configuracion', TTL_CATALOGOS, lambda: _datos(RolSerializer, selectors.listar_roles())))


class EtiquetasView(APIView):
    permission_classes = [AdminParaEscritura]

    @extend_schema(summary='Listar etiquetas', tags=[TAG], responses=EtiquetaSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(cached('etiquetas:por-id', TTL_CATALOGOS, lambda: _datos(EtiquetaSerializer, selectors.listar_etiquetas())))

    @extend_schema(
        summary='Crear o editar una etiqueta',
        tags=[TAG],
        request=SaveEtiquetaRequestSerializer,
        responses={201: EtiquetaSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = SaveEtiquetaRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        etiqueta = services.guardar_etiqueta(
            data.get('id'), data['etiquetaNombre'], data.get('parent_id'), data['rolesPermitidos']
        )
        return Response(EtiquetaSerializer(etiqueta).data, status=status.HTTP_201_CREATED)


class EtiquetaDetailView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Eliminar una etiqueta', tags=[TAG], responses={204: None})
    def delete(self, request: Request, etiqueta_id: int) -> Response:
        services.eliminar_etiqueta(etiqueta_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EtiquetaRolesView(APIView):
    @extend_schema(summary='Listar roles permitidos por etiqueta', tags=[TAG], responses=EtiquetaRolSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(
            cached('etiquetas:roles', TTL_CATALOGOS, lambda: _datos(EtiquetaRolSerializer, selectors.listar_etiqueta_roles()))
        )


class ImagenesView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AdminParaEscritura]

    @extend_schema(summary='Listar imágenes del carrusel institucional', tags=[TAG], responses=ImagenSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(
            cached('configuracion-imagenes:lista', TTL_CATALOGOS, lambda: _datos(ImagenSerializer, selectors.listar_imagenes()))
        )

    @extend_schema(summary='Subir una imagen nueva al carrusel', tags=[TAG], responses={201: ImagenSerializer})
    def post(self, request: Request) -> Response:
        archivo = request.FILES.get('file')
        if archivo is None:
            raise ValidationError({'file': 'Este campo es requerido.'})
        imagen = services.crear_imagen_carrusel(archivo)
        return Response(ImagenSerializer(imagen).data, status=status.HTTP_201_CREATED)


class ImagenDetailView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Cambiar el puesto (1-4) de una imagen del carrusel', tags=[TAG], responses=ImagenSerializer)
    def patch(self, request: Request, imagen_id: int) -> Response:
        puesto = request.data.get('puesto')
        if puesto is None:
            raise ValidationError({'puesto': 'Este campo es requerido.'})
        try:
            puesto = int(puesto)
        except (TypeError, ValueError):
            raise ValidationError({'puesto': 'El puesto debe ser un número del 1 al 4.'})
        imagen = services.actualizar_puesto_imagen(imagen_id, puesto)
        return Response(ImagenSerializer(imagen).data)

    @extend_schema(summary='Eliminar una imagen del carrusel', tags=[TAG], responses={204: None})
    def delete(self, request: Request, imagen_id: int) -> Response:
        services.eliminar_imagen(imagen_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ComunicadosView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AdminParaEscritura]

    @extend_schema(summary='Listar comunicados', tags=[TAG], responses=ComunicadoSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(
            cached('configuracion-comunicados:lista', TTL_CATALOGOS, lambda: _datos(ComunicadoSerializer, selectors.listar_comunicados()))
        )

    @extend_schema(summary='Publicar un comunicado nuevo', tags=[TAG], responses={201: ComunicadoSerializer})
    def post(self, request: Request) -> Response:
        titulo = request.data.get('titulo')
        contenido = request.data.get('contenido')
        if not titulo or not contenido:
            raise ValidationError({'detail': 'Título y contenido son requeridos.'})
        comunicado = services.guardar_comunicado(request.user, None, titulo, contenido, request.FILES.get('file'))
        return Response(ComunicadoSerializer(comunicado).data, status=status.HTTP_201_CREATED)


class ComunicadoDetailView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Editar un comunicado existente', tags=[TAG], responses=ComunicadoSerializer)
    def patch(self, request: Request, comunicado_id: int) -> Response:
        titulo = request.data.get('titulo')
        contenido = request.data.get('contenido')
        if not titulo or not contenido:
            raise ValidationError({'detail': 'Título y contenido son requeridos.'})
        comunicado = services.guardar_comunicado(request.user, comunicado_id, titulo, contenido, request.FILES.get('file'))
        return Response(ComunicadoSerializer(comunicado).data)

    @extend_schema(summary='Eliminar un comunicado', tags=[TAG], responses={204: None})
    def delete(self, request: Request, comunicado_id: int) -> Response:
        services.eliminar_comunicado(comunicado_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActividadesView(APIView):
    permission_classes = [AdminParaEscritura]

    @extend_schema(summary='Listar actividades del calendario', tags=[TAG], responses=ActividadSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(
            cached('configuracion-actividades:lista', TTL_CATALOGOS, lambda: _datos(ActividadSerializer, selectors.listar_actividades()))
        )

    @extend_schema(summary='Crear una actividad nueva', tags=[TAG], request=ActividadWriteSerializer, responses={201: ActividadSerializer})
    def post(self, request: Request) -> Response:
        serializer = ActividadWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actividad = services.crear_actividad(request.user, **serializer.validated_data)
        return Response(ActividadSerializer(actividad).data, status=status.HTTP_201_CREATED)


class ActividadDetailView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Editar una actividad', tags=[TAG], request=ActividadWriteSerializer, responses=ActividadSerializer)
    def patch(self, request: Request, actividad_id: int) -> Response:
        serializer = ActividadWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # Con `partial=True` DRF no rellena lo que no llegó: `validated_data` trae solo los campos enviados.
        actividad = services.actualizar_actividad(request.user, actividad_id, dict(serializer.validated_data))
        return Response(ActividadSerializer(actividad).data)

    @extend_schema(summary='Eliminar una actividad', tags=[TAG], responses={204: None})
    def delete(self, request: Request, actividad_id: int) -> Response:
        services.eliminar_actividad(request.user, actividad_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CumpleañosView(APIView):
    @extend_schema(summary='Usuarios que cumplen años en el mes actual', tags=[TAG], responses=CumpleañoSerializer(many=True))
    def get(self, request: Request) -> Response:
        mes = selectors.mes_actual()
        return Response(
            cached(f'cumpleanos:{mes}', TTL_CATALOGOS, lambda: _datos(CumpleañoSerializer, selectors.listar_cumpleanos_del_mes()))
        )
