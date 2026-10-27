"""
Matriz de permisos: quién puede llamar a cada endpoint, método por método.

La tabla `ACCESO` se escribe a mano a propósito: cada endpoint nuevo (o cada método nuevo de uno existente) hace
fallar `test_la_tabla_cubre_todas_las_rutas` hasta que alguien decida y anote quién puede usarlo. Después, las pruebas
llaman de verdad a cada ruta como anónimo, como usuario normal y como administrador y comprueban que coincide.
"""

from django.urls import URLPattern, URLResolver, get_resolver, reverse
from rest_framework.test import APIClient

from apps.core.testing import ApiTestCase, cliente_de

PUBLICO = 'publico'  # sin sesión
AUTENTICADO = 'autenticado'  # cualquier persona con sesión; lo que ve lo acota el servidor (por rol o por entidad)
ADMIN = 'admin'  # solo rol Administrador

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
    'usuarios-list-create': ((), {'GET': ADMIN, 'POST': ADMIN}),
    'usuarios-directorio': ((), {'GET': AUTENTICADO}),
    'usuarios-detail': ((ID_INEXISTENTE,), {'GET': ADMIN, 'PATCH': ADMIN}),
    'usuarios-restablecer-password': ((ID_INEXISTENTE,), {'POST': ADMIN}),
    'usuarios-roles': ((), {'GET': AUTENTICADO}),
    'usuarios-financieras': ((), {'GET': AUTENTICADO}),
    'usuarios-corporaciones': ((), {'GET': AUTENTICADO}),
    'financiero-catalogos': ((), {'GET': AUTENTICADO}),
    'financiero-resumen': ((), {'GET': AUTENTICADO}),
    'financiero-notificaciones': ((), {'GET': AUTENTICADO}),
    'financiero-periodo': ((), {'GET': AUTENTICADO}),
    'financiero-exportar': ((), {'GET': AUTENTICADO}),
    'financiero-documentos': ((), {'GET': AUTENTICADO, 'POST': AUTENTICADO}),
    'financiero-historial': ((ID_INEXISTENTE,), {'GET': AUTENTICADO}),
    'financiero-aprobar': ((ID_INEXISTENTE,), {'POST': ADMIN}),
    'financiero-rechazar': ((ID_INEXISTENTE,), {'POST': ADMIN}),
    'financiero-revocar': ((ID_INEXISTENTE,), {'POST': ADMIN}),
    'financiero-rango-fechas': ((), {'POST': ADMIN}),
    'documentos-categorias': ((), {'GET': AUTENTICADO, 'POST': ADMIN}),
    'documentos-categoria-detalle': ((ID_INEXISTENTE,), {'PUT': ADMIN, 'PATCH': ADMIN, 'DELETE': ADMIN}),
    'documentos-etiquetas': ((), {'GET': AUTENTICADO}),
    'documentos-docs-etiquetas': ((), {'GET': AUTENTICADO}),
    'documentos-documentos': ((), {'GET': AUTENTICADO, 'POST': ADMIN}),
    'documentos-exportar': ((), {'GET': AUTENTICADO}),
    'documentos-reemplazar': ((ID_INEXISTENTE,), {'POST': ADMIN}),
    'configuracion-roles': ((), {'GET': AUTENTICADO}),
    'configuracion-etiquetas': ((), {'GET': AUTENTICADO, 'POST': ADMIN}),
    'configuracion-etiqueta-detail': ((ID_INEXISTENTE,), {'DELETE': ADMIN}),
    'configuracion-etiqueta-roles': ((), {'GET': AUTENTICADO}),
    'configuracion-imagenes': ((), {'GET': AUTENTICADO, 'POST': ADMIN}),
    'configuracion-imagen-detail': ((ID_INEXISTENTE,), {'PATCH': ADMIN, 'DELETE': ADMIN}),
    'configuracion-comunicados': ((), {'GET': AUTENTICADO, 'POST': ADMIN}),
    'configuracion-comunicado-detail': ((ID_INEXISTENTE,), {'PATCH': ADMIN, 'DELETE': ADMIN}),
    'configuracion-actividades': ((), {'GET': AUTENTICADO, 'POST': ADMIN}),
    'configuracion-actividad-detail': ((ID_INEXISTENTE,), {'PATCH': ADMIN, 'DELETE': ADMIN}),
    'configuracion-bitacora': ((), {'GET': ADMIN}),
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

    def test_un_usuario_normal_no_entra_a_lo_de_administrador(self):
        for nombre, metodo, nivel in self._casos():
            with self.subTest(ruta=nombre, metodo=metodo):
                estado = _llamar(self.cliente_usuario, metodo, nombre).status_code
                if nivel == ADMIN:
                    self.assertEqual(estado, 403)
                else:
                    self.assertNotIn(estado, (401, 403))

    def test_el_administrador_entra_a_todo(self):
        for nombre, metodo, nivel in self._casos():
            if nivel == PUBLICO:
                continue
            with self.subTest(ruta=nombre, metodo=metodo):
                estado = _llamar(self.cliente_admin, metodo, nombre).status_code
                self.assertNotIn(estado, (401, 403))

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

        from apps.core.testing import crear_usuario

        inactivo = crear_usuario(estado='I', email='inactivo@inversa.hn')
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(inactivo)}')

        self.assertEqual(cliente.get(reverse('me')).status_code, 401)
        self.assertEqual(cliente.get(reverse('usuarios-directorio')).status_code, 401)
