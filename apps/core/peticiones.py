"""Tipos para las vistas: solo ayudan al editor y al verificador de tipos; en ejecución DRF entrega una `Request` normal."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from rest_framework.exceptions import ValidationError
from rest_framework.request import Request

if TYPE_CHECKING:
    from apps.usuarios.models import Usuario


class PeticionAutenticada(Request):
    """
    Petición de una vista que exige sesión (`permission_classes` no deja pasar a nadie anónimo): `user` es siempre una
    persona (`Usuario`). Sin esto, el tipo de `request.user` es «una persona o alguien anónimo» y ningún servicio lo acepta.
    """

    user: 'Usuario'  # type: ignore[assignment]


def cuerpo_como_diccionario(request: Request) -> Mapping[str, Any]:
    """El cuerpo de la petición como diccionario; si llega otra cosa (una lista, por ejemplo) es un 400, no un error del servidor."""
    if not isinstance(request.data, Mapping):
        raise ValidationError({'detail': 'El cuerpo de la petición debe ser un objeto.'})
    return request.data
