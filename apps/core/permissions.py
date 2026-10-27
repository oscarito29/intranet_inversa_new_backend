"""
Qué puede hacer cada rol. Es la única tabla de permisos del sistema: las vistas piden un permiso (`requiere`), no un
número de rol, así que agregar o ajustar un rol se hace aquí, con su prueba, y no en cada vista.

Los permisos dicen QUÉ se puede hacer; sobre QUÉ entidades lo decide `apps/usuarios/alcance.py`.
"""

from enum import StrEnum

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

ROL_ADMIN = 1
ROL_USUARIO = 2
ROL_APROBADOR = 3
ROL_CONSULTA = 4
# El número 5 NO se usa para ningún rol: el sistema PHP anterior lo trata como administrador (`in_array($rol, [1, 5])`)
# y mientras conviva con este, una persona con el rol 5 vería sus menús de administración.
ROL_RESERVADO_POR_EL_PHP = 5


class Permiso(StrEnum):
    FINANCIERO_VER_TODAS = 'financiero.ver_todas'  # ver los estados de todas las entidades (sin él, solo las suyas)
    FINANCIERO_SUBIR = 'financiero.subir'  # subir estados a sus entidades (con VER_TODAS, a cualquiera)
    FINANCIERO_APROBAR = 'financiero.aprobar'  # aprobar, rechazar y revocar
    FINANCIERO_RANGO_FECHAS = 'financiero.rango_fechas'  # fijar la ventana de subida
    FINANCIERO_EXPORTAR = 'financiero.exportar'  # exportar el periodo a Excel
    DOCUMENTOS_VER_TODOS = 'documentos.ver_todos'  # sin él, solo los documentos de las etiquetas de su rol
    DOCUMENTOS_GESTIONAR = 'documentos.gestionar'  # subir y reemplazar documentos, y las categorías
    CONTENIDO_GESTIONAR = 'contenido.gestionar'  # comunicados, carrusel, actividades y etiquetas
    USUARIOS_GESTIONAR = 'usuarios.gestionar'  # crear y editar personas, roles y entidades
    BITACORA_VER = 'bitacora.ver'


PERMISOS_POR_ROL: dict[int, frozenset[Permiso]] = {
    ROL_ADMIN: frozenset(Permiso),
    ROL_APROBADOR: frozenset({Permiso.FINANCIERO_VER_TODAS, Permiso.FINANCIERO_APROBAR, Permiso.FINANCIERO_EXPORTAR}),
    ROL_CONSULTA: frozenset({Permiso.FINANCIERO_VER_TODAS, Permiso.FINANCIERO_EXPORTAR}),
    ROL_USUARIO: frozenset({Permiso.FINANCIERO_SUBIR}),
}


def permisos_del_rol(rol_id: int | None) -> frozenset[Permiso]:
    """Un rol que no está en la tabla (por ejemplo, uno que alguien agregue a la base sin pasar por aquí) no puede nada."""
    return PERMISOS_POR_ROL.get(rol_id, frozenset())


def tiene_permiso(usuario, permiso: Permiso) -> bool:
    return bool(usuario and getattr(usuario, 'is_authenticated', False) and permiso in permisos_del_rol(usuario.rol_id))


def permisos_de(usuario) -> list[str]:
    """Lo que el frontend usa para mostrar u ocultar menús y botones (el servidor vuelve a comprobarlo siempre)."""
    return sorted(str(permiso) for permiso in permisos_del_rol(usuario.rol_id))


def roles_con(permiso: Permiso) -> list[int]:
    return sorted(rol for rol, permisos in PERMISOS_POR_ROL.items() if permiso in permisos)


def requiere(permiso: Permiso, *, solo_escritura: bool = False) -> type[BasePermission]:
    """
    Clase de permiso para `permission_classes`. Con `solo_escritura`, cualquier persona autenticada puede leer
    y solo quien tiene el permiso crea, edita o elimina.
    """

    class Requiere(BasePermission):
        message = 'No tienes permiso para realizar esta acción.'

        def has_permission(self, request: Request, view: APIView) -> bool:
            usuario = request.user
            if not (usuario and usuario.is_authenticated):
                return False
            if solo_escritura and request.method in SAFE_METHODS:
                return True
            return tiene_permiso(usuario, permiso)

    Requiere.__name__ = Requiere.__qualname__ = f'Requiere[{permiso.value}{", escritura" if solo_escritura else ""}]'
    return Requiere
