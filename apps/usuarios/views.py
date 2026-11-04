from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import AuthenticationFailed, Throttled, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.bitacora import registrar_bitacora
from apps.core.peticiones import PeticionAutenticada, cuerpo_como_diccionario

from . import bloqueo, services
from .models import Usuario
from .serializers import (
    CambiarPasswordSerializer,
    LoginSerializer,
    PerfilSerializer,
    PerfilUpdateSerializer,
    UsuarioSerializer,
)

TAG = 'Autenticación'
RUTA_COOKIE = '/api/v1/auth/'


def _refresh_de(texto: str) -> RefreshToken:
    """SimpleJWT acepta el texto del token, aunque su anotación de tipo diga que solo recibe un `Token`."""
    return RefreshToken(texto)  # type: ignore[arg-type]


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        path=RUTA_COOKIE,
    )


class LoginView(TokenObtainPairView):
    """POST /api/v1/auth/token/ — autentica contra la tabla `user` existente."""

    serializer_class = LoginSerializer
    permission_classes = (permissions.AllowAny,)
    # Tope por dirección, aparte del bloqueo por correo: frena a quien prueba muchos correos desde un mismo lugar.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    @extend_schema(
        summary='Iniciar sesión',
        description='Devuelve un access token y setea el refresh token como cookie httpOnly.',
        tags=[TAG],
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        correo = str(cuerpo_como_diccionario(request).get('email', '')).strip().lower()
        espera = bloqueo.segundos_de_bloqueo(correo)
        if espera:
            raise Throttled(wait=espera)

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed:
            if bloqueo.registrar_fallo(correo):
                registrar_bitacora(correo, 'Bloqueo', 'Acceso bloqueado por intentos fallidos de inicio de sesión')
                raise Throttled(wait=bloqueo.BLOQUEO_SEGUNDOS) from None
            raise

        bloqueo.limpiar(correo)
        data = serializer.validated_data
        refresh_token = str(data.pop('refresh'))
        registrar_bitacora(data['user']['email'], 'Login', 'Inicia sesión')

        response = Response({'access': str(data['access']), 'user': data['user']}, status=status.HTTP_200_OK)
        _set_refresh_cookie(response, refresh_token)
        return response


class RefreshView(APIView):
    """POST /api/v1/auth/token/refresh/ — usa el refresh token de la cookie httpOnly, no del body."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(summary='Refrescar access token', tags=[TAG])
    def post(self, request: Request) -> Response:
        raw_refresh_token = request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME)
        if not raw_refresh_token:
            raise ValidationError({'detail': 'No hay sesión activa.'})

        try:
            usuario_id = _refresh_de(raw_refresh_token)['user_id']
            if not Usuario.objects.filter(pk=usuario_id, estado='A').exists():
                raise TokenError('Usuario inactivo.')
            serializer = TokenRefreshSerializer(data={'refresh': raw_refresh_token})
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken) as exc:
            raise ValidationError({'detail': 'La sesión expiró, vuelve a iniciar sesión.'}) from exc

        datos = serializer.validated_data
        response = Response({'access': str(datos['access'])})
        if 'refresh' in datos:
            _set_refresh_cookie(response, str(datos['refresh']))
        return response


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — pone el refresh token en lista negra y limpia la cookie."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(summary='Cerrar sesión', tags=[TAG], responses={204: None})
    def post(self, request: Request) -> Response:
        raw_refresh_token = request.COOKIES.get(settings.REFRESH_TOKEN_COOKIE_NAME)
        if raw_refresh_token:
            try:
                token = _refresh_de(raw_refresh_token)
                correo = Usuario.objects.filter(pk=token['user_id']).values_list('email', flat=True).first()
                token.blacklist()
                if correo:
                    registrar_bitacora(correo, 'Logout', 'Cierra sesión')
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.REFRESH_TOKEN_COOKIE_NAME, path=RUTA_COOKIE)
        return response


class PerfilView(APIView):
    """GET/PATCH /api/v1/auth/perfil/ — datos editables del propio usuario."""

    @extend_schema(summary='Perfil del usuario autenticado', tags=[TAG], responses=PerfilSerializer)
    def get(self, request: PeticionAutenticada) -> Response:
        return Response(PerfilSerializer(request.user).data)

    @extend_schema(
        summary='Actualizar nombre, celular y correo',
        tags=[TAG],
        request=PerfilUpdateSerializer,
        responses=PerfilSerializer,
    )
    def patch(self, request: PeticionAutenticada) -> Response:
        serializer = PerfilUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        usuario = services.actualizar_perfil(request.user, datos['name'], datos['phone_number'], datos.get('email'))
        return Response(PerfilSerializer(usuario).data)


class PerfilFotoView(APIView):
    """POST /api/v1/auth/perfil/foto/ — sube la foto de perfil (jpg/png/webp, hasta 2MB)."""

    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary='Subir foto de perfil', tags=[TAG], responses=PerfilSerializer)
    def post(self, request: PeticionAutenticada) -> Response:
        archivo = request.FILES.get('picture')
        if archivo is None:
            raise ValidationError({'picture': 'Selecciona una imagen.'})
        usuario = services.guardar_foto_perfil(request.user, archivo)
        return Response(PerfilSerializer(usuario).data)


class CambiarPasswordView(APIView):
    """POST /api/v1/auth/password/ — cambio de contraseña verificando la actual."""

    # Quien tiene un token robado no debe poder adivinar la contraseña actual a fuerza bruta.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password'

    @extend_schema(
        summary='Cambiar contraseña',
        tags=[TAG],
        request=CambiarPasswordSerializer,
        responses={204: None},
    )
    def post(self, request: PeticionAutenticada) -> Response:
        serializer = CambiarPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        services.cambiar_password(request.user, datos['actual'], datos['nuevo'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/v1/auth/me/ — datos del usuario autenticado."""

    @extend_schema(summary='Usuario autenticado actual', tags=[TAG], responses=UsuarioSerializer)
    def get(self, request: PeticionAutenticada) -> Response:
        return Response(UsuarioSerializer(request.user).data)
