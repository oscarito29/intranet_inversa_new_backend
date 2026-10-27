from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _mensajes_de_django(exc: DjangoValidationError):
    """Forma DRF sin los corchetes que produce `str(DjangoValidationError)`."""
    if hasattr(exc, 'error_dict'):
        return exc.message_dict
    return {'detail': ' '.join(exc.messages)}


def custom_exception_handler(exc, context):
    if isinstance(exc, ObjectDoesNotExist):
        exc = NotFound('El registro solicitado no existe.')
    elif isinstance(exc, DjangoValidationError):
        exc = ValidationError(_mensajes_de_django(exc))
    elif isinstance(exc, IntegrityError):
        return Response(
            {'detail': 'El registro ya existe o viola una regla de la base de datos.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return drf_exception_handler(exc, context)
