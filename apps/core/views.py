import logging

from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class SaludView(APIView):
    """
    ¿Está vivo el servidor y alcanza lo que necesita? Lo consultan el balanceador y el monitoreo, sin sesión.

    Responde solo `ok` o `falla` por componente: nunca el mensaje del error, que puede traer el servidor o el usuario
    de la base. El detalle va al log.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict, 503: dict}, summary='Estado del servidor', tags=['Sistema'])
    def get(self, request):
        componentes = {'base_de_datos': self._base_de_datos(), 'cache': self._cache()}
        sano = all(estado == 'ok' for estado in componentes.values())
        return Response(
            {'estado': 'ok' if sano else 'falla', **componentes},
            status=status.HTTP_200_OK if sano else status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @staticmethod
    def _base_de_datos() -> str:
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        except Exception:
            logger.exception('Salud: la base de datos no responde')
            return 'falla'
        return 'ok'

    @staticmethod
    def _cache() -> str:
        try:
            cache.set('salud', 'ok', 10)
            if cache.get('salud') != 'ok':
                raise RuntimeError('la caché no devolvió lo que se guardó')
        except Exception:
            logger.exception('Salud: la caché no responde')
            return 'falla'
        return 'ok'
