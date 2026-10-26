from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.financial.permissions import EsAdministrador

from . import selectors, services
from .serializers import (
    ActividadSerializer,
    ComunicadoSerializer,
    CumpleañoSerializer,
    EtiquetaRolSerializer,
    EtiquetaSerializer,
    ImagenSerializer,
    RolSerializer,
    SaveEtiquetaRequestSerializer,
)


class RolesView(APIView):
    @extend_schema(summary='Listar roles (solo lectura)')
    def get(self, request: Request) -> Response:
        return Response(RolSerializer(selectors.listar_roles(), many=True).data)


class EtiquetasView(APIView):
    @extend_schema(summary='Listar etiquetas')
    def get(self, request: Request) -> Response:
        return Response(EtiquetaSerializer(selectors.listar_etiquetas(), many=True).data)

    @extend_schema(summary='Crear o editar una etiqueta', request=SaveEtiquetaRequestSerializer)
    def post(self, request: Request) -> Response:
        if request.user.rol_id != 1:
            return Response({'detail': 'Solo un administrador puede modificar etiquetas.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = SaveEtiquetaRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        etiqueta = services.guardar_etiqueta(
            data.get('id'), data['etiquetaNombre'], data.get('parent_id'), data['rolesPermitidos']
        )
        return Response(EtiquetaSerializer(etiqueta).data, status=status.HTTP_201_CREATED)


class EtiquetaDetailView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Eliminar una etiqueta')
    def delete(self, request: Request, etiqueta_id: int) -> Response:
        services.eliminar_etiqueta(etiqueta_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EtiquetaRolesView(APIView):
    @extend_schema(summary='Listar roles permitidos por etiqueta')
    def get(self, request: Request) -> Response:
        return Response(EtiquetaRolSerializer(selectors.listar_etiqueta_roles(), many=True).data)


class ImagenesView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary='Listar imágenes del carrusel institucional')
    def get(self, request: Request) -> Response:
        return Response(ImagenSerializer(selectors.listar_imagenes(), many=True).data)

    @extend_schema(summary='Subir una imagen nueva al carrusel')
    def post(self, request: Request) -> Response:
        if request.user.rol_id != 1:
            return Response({'detail': 'Solo un administrador puede subir imágenes.'}, status=status.HTTP_403_FORBIDDEN)
        archivo = request.FILES.get('file')
        if archivo is None:
            raise DrfValidationError({'file': 'Este campo es requerido.'})
        try:
            imagen = services.crear_imagen_carrusel(archivo)
        except DjangoValidationError as exc:
            raise DrfValidationError(str(exc)) from exc
        return Response(ImagenSerializer(imagen).data, status=status.HTTP_201_CREATED)


class ImagenDetailView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Cambiar el puesto (1-4) de una imagen del carrusel')
    def patch(self, request: Request, imagen_id: int) -> Response:
        puesto = request.data.get('puesto')
        if puesto is None:
            raise DrfValidationError({'puesto': 'Este campo es requerido.'})
        imagen = services.actualizar_puesto_imagen(imagen_id, int(puesto))
        return Response(ImagenSerializer(imagen).data)

    @extend_schema(summary='Eliminar una imagen del carrusel')
    def delete(self, request: Request, imagen_id: int) -> Response:
        services.eliminar_imagen(imagen_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ComunicadosView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary='Listar comunicados')
    def get(self, request: Request) -> Response:
        return Response(ComunicadoSerializer(selectors.listar_comunicados(), many=True).data)

    @extend_schema(summary='Publicar un comunicado nuevo')
    def post(self, request: Request) -> Response:
        if request.user.rol_id != 1:
            return Response({'detail': 'Solo un administrador puede publicar comunicados.'}, status=status.HTTP_403_FORBIDDEN)
        titulo = request.data.get('titulo')
        contenido = request.data.get('contenido')
        archivo = request.FILES.get('file')
        if not titulo or not contenido:
            raise DrfValidationError({'detail': 'Título y contenido son requeridos.'})
        try:
            comunicado = services.guardar_comunicado(request.user, None, titulo, contenido, archivo)
        except (DjangoValidationError, ValueError) as exc:
            raise DrfValidationError(str(exc)) from exc
        return Response(ComunicadoSerializer(comunicado).data, status=status.HTTP_201_CREATED)


class ComunicadoDetailView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [EsAdministrador]

    @extend_schema(summary='Editar un comunicado existente')
    def patch(self, request: Request, comunicado_id: int) -> Response:
        titulo = request.data.get('titulo')
        contenido = request.data.get('contenido')
        archivo = request.FILES.get('file')
        if not titulo or not contenido:
            raise DrfValidationError({'detail': 'Título y contenido son requeridos.'})
        comunicado = services.guardar_comunicado(request.user, comunicado_id, titulo, contenido, archivo)
        return Response(ComunicadoSerializer(comunicado).data)

    @extend_schema(summary='Eliminar un comunicado')
    def delete(self, request: Request, comunicado_id: int) -> Response:
        services.eliminar_comunicado(comunicado_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActividadesView(APIView):
    @extend_schema(summary='Listar actividades del calendario')
    def get(self, request: Request) -> Response:
        return Response(ActividadSerializer(selectors.listar_actividades(), many=True).data)

    @extend_schema(summary='Crear una actividad nueva')
    def post(self, request: Request) -> Response:
        if request.user.rol_id != 1:
            return Response({'detail': 'Solo un administrador puede crear actividades.'}, status=status.HTTP_403_FORBIDDEN)
        data = request.data
        for campo in ('fecha', 'titulo'):
            if not data.get(campo):
                raise DrfValidationError({campo: 'Este campo es requerido.'})
        actividad = services.crear_actividad(
            fecha=data['fecha'],
            titulo=data['titulo'],
            descripcion=data.get('descripcion', ''),
            hora_desde=data.get('hora_desde') or None,
            hora_hasta=data.get('hora_hasta') or None,
        )
        return Response(ActividadSerializer(actividad).data, status=status.HTTP_201_CREATED)


class CumpleañosView(APIView):
    @extend_schema(summary='Usuarios que cumplen años en el mes actual')
    def get(self, request: Request) -> Response:
        return Response(CumpleañoSerializer(selectors.listar_cumpleanos_del_mes(), many=True).data)
