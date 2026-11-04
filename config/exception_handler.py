from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import NotFound, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _mensajes_de_django(exc: DjangoValidationError):
    """Forma DRF sin los corchetes que produce `str(DjangoValidationError)`."""
    if hasattr(exc, 'error_dict'):
        return exc.message_dict
    return {'detail': ' '.join(exc.messages)}


def _mensaje_de_espera(segundos: int | None) -> str:
    if not segundos:
        return 'Demasiados intentos. Espera un momento e inténtalo de nuevo.'
    if segundos < 90:
        return f'Demasiados intentos. Espera {segundos} segundos e inténtalo de nuevo.'
    minutos = -(-segundos // 60)
    return f'Demasiados intentos. Espera {minutos} minutos e inténtalo de nuevo.'


def custom_exception_handler(exc, context):
    if isinstance(exc, Throttled):
        espera = getattr(exc, 'wait', None)
        exc = Throttled(wait=espera, detail=_mensaje_de_espera(int(espera) if espera else None))
    elif isinstance(exc, ObjectDoesNotExist):
        exc = NotFound('El registro solicitado no existe.')
    elif isinstance(exc, DjangoValidationError):
        exc = ValidationError(_mensajes_de_django(exc))
    elif isinstance(exc, IntegrityError):
        return Response(
            {'detail': 'El registro ya existe o viola una regla de la base de datos.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return drf_exception_handler(exc, context)
