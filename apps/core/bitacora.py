from django.utils import timezone

from apps.financial.models import Bitacora


def registrar_bitacora(usuario_email: str, accion: str, descripcion: str) -> None:
    Bitacora.objects.create(
        usuario=usuario_email[:100],
        accion=accion[:100],
        descripcion=descripcion[:100],
        fecha=timezone.now(),
    )
