"""
Matriz de permisos: quién puede llamar a cada endpoint, método por método y rol por rol.

La tabla `ACCESO` se escribe a mano a propósito: cada endpoint nuevo (o cada método nuevo de uno existente) hace
fallar `test_la_tabla_cubre_todas_las_rutas` hasta que alguien decida y anote qué permiso pide. Después, las pruebas
llaman de verdad a cada ruta como anónimo y como una persona de cada rol, y comprueban que coincide con
`PERMISOS_ESPERADOS`, que también se escribe a mano: cambiar lo que un rol puede hacer exige cambiarlo aquí a propósito.
"""

from django.urls import URLPattern, URLResolver, get_resolver, reverse
from rest_framework.test import APIClient

from apps.core.permissions import PERMISOS_POR_ROL, ROL_ADMIN, ROL_APROBADOR, ROL_CONSULTA, ROL_USUARIO, Permiso
from apps.core.testing import ApiTestCase, cliente_de, crear_usuario

PUBLICO = 'publico'  # sin sesión
AUTENTICADO = 'autenticado'  # cualquier persona con sesión; lo que ve lo acota el servidor (por rol o por entidad)
# Cualquier otro valor es un `Permiso`: solo los roles que lo tienen pueden llamar a esa ruta.

# Lo que cada rol puede hacer. Es la tabla de `PLAN_MEJORAS.md` (3.12), copiada a mano.
PERMISOS_ESPERADOS = {
    ROL_ADMIN: set(Permiso),
    ROL_APROBADOR: {Permiso.FINANCIERO_VER_TODAS, Permiso.FINANCIERO_APROBAR, Permiso.FINANCIERO_EXPORTAR},
    ROL_CONSULTA: {Permiso.FINANCIERO_VER_TODAS, Permiso.FINANCIERO_EXPORTAR},
    ROL_USUARIO: {Permiso.FINANCIERO_SUBIR},
}
NOMBRES_DE_ROL = {ROL_ADMIN: 'Administrador', ROL_APROBADOR: 'Aprobador', ROL_CONSULTA: 'Consulta', ROL_USUARIO: 'Usuario'}

ID_INEXISTENTE = 999_999

# nombre de la ruta → argumentos de la URL y, por método, quién puede llamarla
ACCESO: dict[str, tuple[tuple, dict[str, str]]] = {
    'salud': ((), {'GET': PUBLICO}),
    'token_obtain_pair': ((), {'POST': PUBLICO}),
    'token_refresh': ((), {'POST': PUBLICO}),
    'logout': ((), {'POST': PUBLICO}),
    'me': ((), {'GET': AUTENTICADO}),
    'perfil': ((), {'GET': AUTENTICADO, 'PATCH': AUTENTICADO}),
    'perfil-foto': ((), {'POST': AUTENTICADO}),
    'cambiar-password': ((), {'POST': AUTENTICADO}),
    'usuarios-list-create': ((), {'GET': Permiso.USUARIOS_GESTIONAR, 'POST': Permiso.USUARIOS_GESTIONAR}),
    'usuarios-directorio': ((), {'GET': AUTENTICADO}),
    'usuarios-detail': ((ID_INEXISTENTE,), {'GET': Permiso.USUARIOS_GESTIONAR, 'PATCH': Permiso.USUARIOS_GESTIONAR}),
    'usuarios-restablecer-password': ((ID_INEXISTENTE,), {'POST': Permiso.USUARIOS_GESTIONAR}),
    'usuarios-roles': ((), {'GET': AUTENTICADO}),
    'usuarios-financieras': ((), {'GET': AUTENTICADO}),
    'usuarios-corporaciones': ((), {'GET': AUTENTICADO}),
    'financiero-catalogos': ((), {'GET': AUTENTICADO}),
    'financiero-resumen': ((), {'GET': AUTENTICADO}),
    'financiero-notificaciones': ((), {'GET': AUTENTICADO}),
    'financiero-periodo': ((), {'GET': AUTENTICADO}),
    'financiero-exportar': ((), {'GET': Permiso.FINANCIERO_EXPORTAR}),
    'financiero-documentos': ((), {'GET': AUTENTICADO, 'POST': Permiso.FINANCIERO_SUBIR}),
    'financiero-historial': ((ID_INEXISTENTE,), {'GET': AUTENTICADO}),
    'financiero-aprobar': ((ID_INEXISTENTE,), {'POST': Permiso.FINANCIERO_APROBAR}),
    'financiero-rechazar': ((ID_INEXISTENTE,), {'POST': Permiso.FINANCIERO_APROBAR}),
    'financiero-revocar': ((ID_INEXISTENTE,), {'POST': Permiso.FINANCIERO_APROBAR}),
    'financiero-rango-fechas': ((), {'POST': Permiso.FINANCIERO_RANGO_FECHAS}),
    'documentos-categorias': ((), {'GET': AUTENTICADO, 'POST': Permiso.DOCUMENTOS_GESTIONAR}),
    'documentos-categoria-detalle': ((ID_INEXISTENTE,), {'PUT': Permiso.DOCUMENTOS_GESTIONAR, 'PATCH': Permiso.DOCUMENTOS_GESTIONAR, 'DELETE': Permiso.DOCUMENTOS_GESTIONAR}),
    'documentos-etiquetas': ((), {'GET': AUTENTICADO}),
    'documentos-docs-etiquetas': ((), {'GET': AUTENTICADO}),
    'documentos-documentos': ((), {'GET': AUTENTICADO, 'POST': Permiso.DOCUMENTOS_GESTIONAR}),
    'documentos-exportar': ((), {'GET': AUTENTICADO}),
    'documentos-reemplazar': ((ID_INEXISTENTE,), {'POST': Permiso.DOCUMENTOS_GESTIONAR}),
    'configuracion-roles': ((), {'GET': AUTENTICADO}),
    'configuracion-etiquetas': ((), {'GET': AUTENTICADO, 'POST': Permiso.CONTENIDO_GESTIONAR}),
    'configuracion-etiqueta-detail': ((ID_INEXISTENTE,), {'DELETE': Permiso.CONTENIDO_GESTIONAR}),
    'configuracion-etiqueta-roles': ((), {'GET': AUTENTICADO}),
    'configuracion-imagenes': ((), {'GET': AUTENTICADO, 'POST': Permiso.CONTENIDO_GESTIONAR}),
    'configuracion-imagen-detail': ((ID_INEXISTENTE,), {'PATCH': Permiso.CONTENIDO_GESTIONAR, 'DELETE': Permiso.CONTENIDO_GESTIONAR}),
    'configuracion-comunicados': ((), {'GET': AUTENTICADO, 'POST': Permiso.CONTENIDO_GESTIONAR}),
    'configuracion-comunicado-detail': ((ID_INEXISTENTE,), {'PATCH': Permiso.CONTENIDO_GESTIONAR, 'DELETE': Permiso.CONTENIDO_GESTIONAR}),
    'configuracion-actividades': ((), {'GET': AUTENTICADO, 'POST': Permiso.CONTENIDO_GESTIONAR}),
    'configuracion-actividad-detail': ((ID_INEXISTENTE,), {'PATCH': Permiso.CONTENIDO_GESTIONAR, 'DELETE': Permiso.CONTENIDO_GESTIONAR}),
    'configuracion-bitacora': ((), {'GET': Permiso.BITACORA_VER}),
    'configuracion-cumpleanos': ((), {'GET': AUTENTICADO}),
}

# Documentación de la API: su exposición se decide por configuración (ver `API_DOCS_ENABLED`), no por rol.
DOCUMENTACION = {'schema', 'swagger-ui'}


def _rutas() -> dict[str, set[str]]:
    """Nombre de cada ruta de la API → métodos que su vista implementa."""
    encontradas: dict[str, set[str]] = {}

    def recorrer(patrones, prefijo=''):
        for patron in patrones:
            if isinstance(patron, URLResolver):
                recorrer(patron.url_patterns, prefijo + str(patron.pattern))
            elif isinstance(patron, URLPattern) and (prefijo + str(patron.pattern)).startswith('api/'):
                clase = getattr(patron.callback, 'cls', None)
                if clase is not None and patron.name:
                    encontradas[patron.name] = {m.upper() for m in clase.http_method_names if m not in ('options', 'head') and hasattr(clase, m)}

    recorrer(get_resolver().url_patterns)
    return encontradas


def _llamar(cliente: APIClient, metodo: str, nombre: str):
    argumentos = ACCESO[nombre][0]
    return getattr(cliente, metodo.lower())(reverse(nombre, args=argumentos), {}, format='json')


class CoberturaDeLaTablaTests(ApiTestCase):
    def test_la_tabla_cubre_todas_las_rutas_y_metodos_de_la_api(self):
        reales = {nombre: metodos for nombre, metodos in _rutas().items() if nombre not in DOCUMENTACION}
        anotadas = {nombre: set(metodos) for nombre, (_, metodos) in ACCESO.items()}

        sin_anotar = {nombre: sorted(metodos) for nombre, metodos in reales.items() if anotadas.get(nombre) != metodos}
        sobrantes = sorted(set(anotadas) - set(reales))

        self.assertEqual(sin_anotar, {}, 'Rutas o métodos que existen y no están en ACCESO: decide quién puede usarlos y anótalos.')
        self.assertEqual(sobrantes, [], 'Rutas anotadas en ACCESO que ya no existen.')


class MatrizDeAccesoTests(ApiTestCase):
    def _casos(self):
        return [(nombre, metodo, nivel) for nombre, (_, metodos) in ACCESO.items() for metodo, nivel in metodos.items()]

    def test_sin_sesion_solo_entran_los_publicos(self):
        anonimo = cliente_de(None)
        for nombre, metodo, nivel in self._casos():
            with self.subTest(ruta=nombre, metodo=metodo):
                estado = _llamar(anonimo, metodo, nombre).status_code
                if nivel == PUBLICO:
                    self.assertNotIn(estado, (401, 403))
                else:
                    self.assertEqual(estado, 401)

    def test_cada_rol_entra_solo_a_lo_que_su_permiso_permite(self):
        for rol, permisos in PERMISOS_ESPERADOS.items():
            cliente = cliente_de(crear_usuario(rol_id=rol, email=f'rol{rol}@inversa.hn'))
            for nombre, metodo, nivel in self._casos():
                if nivel == PUBLICO:
                    continue
                with self.subTest(rol=NOMBRES_DE_ROL[rol], ruta=nombre, metodo=metodo):
                    estado = _llamar(cliente, metodo, nombre).status_code
                    if nivel == AUTENTICADO or nivel in permisos:
                        self.assertNotIn(estado, (401, 403))
                    else:
                        self.assertEqual(estado, 403)

    def test_el_catalogo_de_permisos_es_el_que_se_decidio(self):
        self.assertEqual({rol: set(permisos) for rol, permisos in PERMISOS_POR_ROL.items()}, PERMISOS_ESPERADOS)

    def test_todo_permiso_lo_usa_alguna_ruta_o_el_alcance_de_los_datos(self):
        # Estos dos no protegen una ruta: deciden QUÉ ve la persona dentro de una ruta que ya es de cualquiera.
        de_alcance = {Permiso.FINANCIERO_VER_TODAS, Permiso.DOCUMENTOS_VER_TODOS}
        usados = {nivel for _, metodos in ACCESO.values() for nivel in metodos.values() if isinstance(nivel, Permiso)}

        self.assertEqual(usados | de_alcance, set(Permiso), 'Hay un permiso que ninguna ruta pide: sobra o falta anotarlo en ACCESO.')

    def test_un_token_invalido_es_401_y_no_entra_a_nada(self):
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION='Bearer esto.no.es.un.token')
        for nombre, metodo, nivel in self._casos():
            if nivel == PUBLICO:
                continue
            with self.subTest(ruta=nombre, metodo=metodo):
                self.assertEqual(_llamar(cliente, metodo, nombre).status_code, 401)

    def test_un_usuario_inactivo_con_token_vigente_no_entra(self):
        from rest_framework_simplejwt.tokens import AccessToken

        inactivo = crear_usuario(estado='I', email='inactivo@inversa.hn')
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(inactivo)}')

        self.assertEqual(cliente.get(reverse('me')).status_code, 401)
        self.assertEqual(cliente.get(reverse('usuarios-directorio')).status_code, 401)
