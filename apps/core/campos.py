from rest_framework import serializers

from .archivos import url_de_valor


class ArchivoUrlField(serializers.CharField):
    """Un archivo guardado en la base, mostrado como la dirección para abrirlo (ver `url_de_valor`). Solo de lectura."""

    def __init__(self, **kwargs):
        kwargs.setdefault('read_only', True)
        super().__init__(**kwargs)

    def to_representation(self, valor: str) -> str | None:
        return url_de_valor(valor)
