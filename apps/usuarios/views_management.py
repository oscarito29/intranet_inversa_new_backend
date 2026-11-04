from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import cached
from apps.core.peticiones import PeticionAutenticada
from apps.core.permissions import Permiso, requiere

from . import selectors, services
from .models import Corporacion, Financiera, Rol
from .serializers import (
    CorporacionSerializer,
    DirectorioConsultaSerializer,
    DirectorioSerializer,
    FinancieraSerializer,
    PasswordTemporalSerializer,
    RolSerializer,
    UsuarioListSerializer,
    UsuarioWriteSerializer,
)

TAG = 'Usuarios'
TTL_CATALOGOS = 60 * 5


class RolesListView(APIView):
    """GET /api/v1/usuarios/roles/ — catálogo de roles (hoy: Admin, User)."""

    @extend_schema(summary='Listar roles', tags=[TAG], responses=RolSerializer(many=True))
    def get(self, request: PeticionAutenticada) -> Response:
        datos = cached('usuarios-catalogos:roles', TTL_CATALOGOS, lambda: list(RolSerializer(Rol.objects.all(), many=True).data))
        return Response(datos)


class FinancierasListView(APIView):
    """GET /api/v1/usuarios/financieras/ — catálogo de financieras/entidades."""

    @extend_schema(summary='Listar financieras', tags=[TAG], responses=FinancieraSerializer(many=True))
    def get(self, request: PeticionAutenticada) -> Response:
        datos = cached(
            'usuarios-catalogos:financieras',
            TTL_CATALOGOS,
            lambda: list(FinancieraSerializer(Financiera.objects.all(), many=True).data),
        )
        return Response(datos)


class CorporacionesListView(APIView):
    """GET /api/v1/usuarios/corporaciones/ — catálogo de corporaciones."""

    @extend_schema(summary='Listar corporaciones', tags=[TAG], responses=CorporacionSerializer(many=True))
    def get(self, request: PeticionAutenticada) -> Response:
        datos = cached(
            'usuarios-catalogos:corporaciones',
            TTL_CATALOGOS,
            lambda: list(CorporacionSerializer(Corporacion.objects.all(), many=True).data),
        )
        return Response(datos)


class DirectorioView(APIView):
    """GET /api/v1/usuarios/directorio/ — cualquier usuario autenticado; solo personas activas y datos de contacto."""

    @extend_schema(
        summary='Directorio de personas',
        description='Personas activas con nombre, correo, celular, entidad y el día y mes de su cumpleaños. Filtra por texto (`q`, '
        'en nombre, correo o entidad) y por entidad (`entidad`). No incluye dirección ni año de nacimiento. Trae hasta 200; '
        '`total` cuenta todas las que coinciden.',
        tags=[TAG],
        parameters=[DirectorioConsultaSerializer],
        responses=DirectorioSerializer,
    )
    def get(self, request: PeticionAutenticada) -> Response:
        consulta = DirectorioConsultaSerializer(data=request.query_params)
        consulta.is_valid(raise_exception=True)
        filtros = consulta.validated_data
        directorio = selectors.listar_directorio(texto=filtros['q'].strip(), financiera_id=filtros['entidad'])
        return Response(DirectorioSerializer(directorio).data)


class UsuariosListCreateView(APIView):
    """GET /api/v1/usuarios/ — listar; POST /api/v1/usuarios/ — crear. Todo el endpoint es de administrador."""

    # La lista trae correo, celular, dirección y fecha de nacimiento de todas las personas: no es para cualquier usuario.
    permission_classes = [requiere(Permiso.USUARIOS_GESTIONAR)]

    @extend_schema(summary='Listar usuarios (solo admin)', tags=[TAG], responses=UsuarioListSerializer(many=True))
    def get(self, request: PeticionAutenticada) -> Response:
        return Response(UsuarioListSerializer(selectors.listar_usuarios(), many=True).data)

    @extend_schema(summary='Crear usuario', tags=[TAG], request=UsuarioWriteSerializer, responses=UsuarioListSerializer)
    def post(self, request: PeticionAutenticada) -> Response:
        serializer = UsuarioWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = services.crear_usuario(request.user, serializer)
        return Response(UsuarioListSerializer(usuario).data, status=status.HTTP_201_CREATED)


class UsuarioDetailView(APIView):
    """GET/PATCH /api/v1/usuarios/{id}/ — ver y editar (solo admin)."""

    permission_classes = [requiere(Permiso.USUARIOS_GESTIONAR)]

    @extend_schema(summary='Ver un usuario', tags=[TAG], responses=UsuarioListSerializer)
    def get(self, request: PeticionAutenticada, pk: int) -> Response:
        return Response(UsuarioListSerializer(selectors.obtener_usuario(pk)).data)

    @extend_schema(summary='Editar usuario', tags=[TAG], request=UsuarioWriteSerializer, responses=UsuarioListSerializer)
    def patch(self, request: PeticionAutenticada, pk: int) -> Response:
        serializer = UsuarioWriteSerializer(selectors.obtener_usuario(pk), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        usuario = services.actualizar_usuario(request.user, serializer)
        return Response(UsuarioListSerializer(usuario).data)


class UsuarioRestablecerPasswordView(APIView):
    """POST /api/v1/usuarios/{id}/restablecer-password/ — asigna una contraseña temporal (solo admin)."""

    permission_classes = [requiere(Permiso.USUARIOS_GESTIONAR)]

    @extend_schema(
        summary='Restablecer la contraseña de un usuario',
        description='Genera una contraseña temporal aleatoria y la devuelve una sola vez, para que el administrador se la entregue al usuario.',
        tags=[TAG],
        request=None,
        responses=PasswordTemporalSerializer,
    )
    def post(self, request: PeticionAutenticada, pk: int) -> Response:
        _, temporal = services.restablecer_password(request.user, pk)
        return Response({'password_temporal': temporal})
