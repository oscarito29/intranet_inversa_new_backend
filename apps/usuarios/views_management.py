from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Corporacion, Financiera, Rol, Usuario
from .permissions import EsAdministrador
from .serializers import (
    CorporacionSerializer,
    FinancieraSerializer,
    RolSerializer,
    UsuarioListSerializer,
    UsuarioWriteSerializer,
)


class RolesListView(APIView):
    """GET /api/v1/usuarios/roles/ — catálogo de roles (hoy: Admin, User)."""

    @extend_schema(summary='Listar roles', responses=RolSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(RolSerializer(Rol.objects.all(), many=True).data)


class FinancierasListView(APIView):
    """GET /api/v1/usuarios/financieras/ — catálogo de financieras/entidades."""

    @extend_schema(summary='Listar financieras', responses=FinancieraSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(FinancieraSerializer(Financiera.objects.all(), many=True).data)


class CorporacionesListView(APIView):
    """GET /api/v1/usuarios/corporaciones/ — catálogo de corporaciones."""

    @extend_schema(summary='Listar corporaciones', responses=CorporacionSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(CorporacionSerializer(Corporacion.objects.all(), many=True).data)


class UsuariosListCreateView(APIView):
    """GET /api/v1/usuarios/ — listar; POST /api/v1/usuarios/ — crear (solo admin)."""

    def get_permissions(self):
        if self.request.method == 'POST':
            return [EsAdministrador()]
        return super().get_permissions()

    @extend_schema(summary='Listar usuarios', responses=UsuarioListSerializer(many=True))
    def get(self, request: Request) -> Response:
        usuarios = Usuario.objects.select_related('rol', 'financiera').order_by('name')
        return Response(UsuarioListSerializer(usuarios, many=True).data)

    @extend_schema(summary='Crear usuario', request=UsuarioWriteSerializer, responses=UsuarioListSerializer)
    def post(self, request: Request) -> Response:
        serializer = UsuarioWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        return Response(UsuarioListSerializer(usuario).data, status=status.HTTP_201_CREATED)


class UsuarioDetailView(APIView):
    """PATCH /api/v1/usuarios/{id}/ — editar (solo admin)."""

    permission_classes = [EsAdministrador]

    @extend_schema(summary='Editar usuario', request=UsuarioWriteSerializer, responses=UsuarioListSerializer)
    def patch(self, request: Request, pk: int) -> Response:
        usuario = get_object_or_404(Usuario, pk=pk)
        serializer = UsuarioWriteSerializer(usuario, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        return Response(UsuarioListSerializer(usuario).data)
