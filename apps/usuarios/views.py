from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import LoginSerializer, UsuarioSerializer


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        path='/api/v1/auth/',
    )


class LoginView(TokenObtainPairView):
    """POST /api/v1/auth/token/ — autentica contra la tabla `user` existente."""

    serializer_class = LoginSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(summary='Iniciar sesión', description='Devuelve un access token y setea el refresh token como cookie httpOnly.')
    def post(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        refresh_token = str(data.pop('refresh'))

        response = Response({'access': str(data['access']), 'user': data['user']}, status=status.HTTP_200_OK)
        _set_refresh_cookie(response, refresh_token)
        return response


class RefreshView(APIView):
    """POST /api/v1/auth/token/refresh/ — usa el refresh token de la cookie httpOnly, no del body."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(summary='Refrescar access token')
    def post(self, request: Request) -> Response:
        raw_refresh_token = request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME)
        if not raw_refresh_token:
            raise ValidationError({'detail': 'No hay sesión activa.'})

        try:
            refresh_token = RefreshToken(raw_refresh_token)
        except TokenError as exc:
            raise ValidationError({'detail': 'La sesión expiró, vuelve a iniciar sesión.'}) from exc

        return Response({'access': str(refresh_token.access_token)})


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — limpia la cookie de refresh token."""

    @extend_schema(summary='Cerrar sesión')
    def post(self, request: Request) -> Response:
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.REFRESH_TOKEN_COOKIE_NAME, path='/api/v1/auth/')
        return response


class MeView(APIView):
    """GET /api/v1/auth/me/ — datos del usuario autenticado."""

    @extend_schema(summary='Usuario autenticado actual', responses=UsuarioSerializer)
    def get(self, request: Request) -> Response:
        return Response(UsuarioSerializer(request.user).data)
