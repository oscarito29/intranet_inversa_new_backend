from django.core.exceptions import ValidationError


class DistintaDeLaActualValidator:
    """La nueva contraseña no puede ser la que la persona ya tiene (cambiarla por la misma no cambia nada)."""

    def validate(self, password: str, user=None) -> None:
        if user is not None and getattr(user, 'pk', None) and user.has_usable_password() and user.check_password(password):
            raise ValidationError('La nueva contraseña no puede ser igual a la actual.', code='password_igual_a_la_actual')

    def get_help_text(self) -> str:
        return 'Debe ser distinta de la contraseña actual.'
