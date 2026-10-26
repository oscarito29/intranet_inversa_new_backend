from django.conf import settings
from django.core.mail import send_mail

from .models import DestinatarioCorreo, Documento


def _destinatarios(documento: Documento) -> list[str]:
    correos = list(DestinatarioCorreo.objects.values_list('email_destinatario', flat=True))
    if documento.email_usuario_sube and documento.email_usuario_sube not in correos:
        correos.append(documento.email_usuario_sube)
    return correos


def notificar_aprobacion(documento: Documento) -> None:
    send_mail(
        subject=f'Aprobación de Estado Financiero {documento.nombre_archivo}',
        message=(
            f'El documento "{documento.nombre_archivo}" fue aprobado por {documento.email_usuario_aprueba}.'
        ),
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@inversa.hn'),
        recipient_list=_destinatarios(documento),
        fail_silently=True,
    )


def notificar_rechazo(documento: Documento) -> None:
    send_mail(
        subject=f'Rechazo de Estado Financiero {documento.nombre_archivo}',
        message=(
            f'El documento "{documento.nombre_archivo}" fue rechazado por {documento.email_usuario_rechaza}.\n\n'
            f'Motivo: {documento.motivo_rechazo}'
        ),
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@inversa.hn'),
        recipient_list=_destinatarios(documento),
        fail_silently=True,
    )


def notificar_revocacion(documento: Documento) -> None:
    send_mail(
        subject=f'Revocación de Estado Financiero {documento.nombre_archivo}',
        message=(
            f'El documento "{documento.nombre_archivo}" fue revocado.\n\n'
            f'Motivo: {documento.motivo_desaprueba}'
        ),
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@inversa.hn'),
        recipient_list=_destinatarios(documento),
        fail_silently=True,
    )
