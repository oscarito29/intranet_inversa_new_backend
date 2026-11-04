from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import Usuario


def cerrar_sesiones(usuario: Usuario) -> int:
    """
    Invalida todos los refresh tokens de la persona: cuando venza su token de acceso (30 minutos) tendrá que volver a
    entrar. Lo que puede hacer ya se lee de la base en cada petición, así que un cambio de rol, entidad o estado
    se aplica al instante en el servidor; esto hace que su pantalla (menú, botones, entidades) se renueve también.
    Devuelve cuántas sesiones cerró.
    """
    pendientes = list(
        OutstandingToken.objects.filter(user_id=usuario.pk, blacklistedtoken__isnull=True).values_list('id', flat=True)
    )
    BlacklistedToken.objects.bulk_create([BlacklistedToken(token_id=token_id) for token_id in pendientes], ignore_conflicts=True)
    return len(pendientes)
