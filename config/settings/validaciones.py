from django.core.exceptions import ImproperlyConfigured

LARGO_MINIMO_CLAVE_SECRETA = 50
CLAVES_DE_EJEMPLO = ('django-insecure', 'change-me')


def exigir_clave_secreta(clave: str) -> str:
    """
    La clave que firma los tokens de sesión. Con una clave conocida (la de ejemplo del repositorio, por ejemplo)
    cualquiera podría fabricar tokens válidos, así que producción se niega a arrancar con ella.
    """
    if clave.startswith(CLAVES_DE_EJEMPLO) or len(clave) < LARGO_MINIMO_CLAVE_SECRETA:
        raise ImproperlyConfigured(
            f'DJANGO_SECRET_KEY debe ser una clave aleatoria de {LARGO_MINIMO_CLAVE_SECRETA} caracteres o más, no la de ejemplo.'
        )
    return clave
