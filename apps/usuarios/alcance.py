"""
Sobre QUÉ entidades puede actuar una persona. El rol dice qué puede hacer (`apps/core/permissions.py`); esto dice dónde.

Una persona tiene una entidad principal (`user.userFinancieraId`) y puede tener entidades adicionales
(`usuario_entidad`). Quien puede ver todas (`financiero.ver_todas`) no se limita por entidad.
Es la única función de alcance del sistema: las consultas financieras, el resumen, las notificaciones y la subida
la usan, para que la regla no se repita (ni se olvide) en cada selector.
"""

from apps.core.permissions import Permiso, tiene_permiso

from .models import Usuario, UsuarioEntidad


def entidades_de(usuario: Usuario) -> frozenset[str]:
    """La entidad principal más las adicionales."""
    adicionales = UsuarioEntidad.objects.filter(usuario_id=usuario.pk).values_list('financiera_id', flat=True)
    return frozenset({str(usuario.financiera_id), *map(str, adicionales)})


def financieras_visibles(usuario: Usuario) -> frozenset[str] | None:
    """Las entidades cuyos estados financieros puede ver; `None` quiere decir todas."""
    if tiene_permiso(usuario, Permiso.FINANCIERO_VER_TODAS):
        return None
    return entidades_de(usuario)


def puede_ver_financiera(usuario: Usuario, financiera_id: str) -> bool:
    visibles = financieras_visibles(usuario)
    return visibles is None or str(financiera_id) in visibles


def puede_subir_a(usuario: Usuario, financiera_id: str) -> bool:
    """Subir exige el permiso de subir y, además, que la entidad sea una de las suyas (o poder ver todas)."""
    return tiene_permiso(usuario, Permiso.FINANCIERO_SUBIR) and puede_ver_financiera(usuario, financiera_id)
