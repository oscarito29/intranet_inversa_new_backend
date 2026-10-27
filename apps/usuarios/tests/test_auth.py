from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.testing import ApiTestCase, crear_usuario, hash_md5_legado
from apps.usuarios.models import Usuario


def _login(cliente: APIClient, email: str, password: str):
    return cliente.post(reverse('token_obtain_pair'), {'email': email, 'password': password}, format='json')


class LoginTests(ApiTestCase):
    def test_login_devuelve_access_usuario_y_cookie_httponly(self):
        respuesta = _login(APIClient(), self.usuario.email, 'Clave-segura-123')

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(set(respuesta.data), {'access', 'user'})
        self.assertEqual(respuesta.data['user']['email'], self.usuario.email)
        cookie = respuesta.cookies[settings.REFRESH_TOKEN_COOKIE_NAME]
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['path'], '/api/v1/auth/')

    def test_login_con_clave_incorrecta_es_401(self):
        self.assertEqual(_login(APIClient(), self.usuario.email, 'otra').status_code, 401)

    def test_usuario_inactivo_no_inicia_sesion(self):
        inactivo = crear_usuario(estado='I', email='inactivo@inversa.hn')
        self.assertEqual(_login(APIClient(), inactivo.email, 'Clave-segura-123').status_code, 401)

    def test_hash_md5_legado_inicia_sesion_y_se_actualiza_a_argon2(self):
        legado = crear_usuario(email='legado@inversa.hn')
        Usuario.objects.filter(pk=legado.pk).update(password=hash_md5_legado('ClaveVieja1'))

        respuesta = _login(APIClient(), 'legado@inversa.hn', 'ClaveVieja1')

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(Usuario.objects.get(pk=legado.pk).password.startswith('argon2'))

    def test_endpoints_protegidos_exigen_token(self):
        self.assertEqual(APIClient().get(reverse('me')).status_code, 401)


class RefreshYLogoutTests(ApiTestCase):
    def _iniciar_sesion(self, usuario=None) -> APIClient:
        cliente = APIClient()
        _login(cliente, (usuario or self.usuario).email, 'Clave-segura-123')
        return cliente

    def test_refresh_devuelve_access_y_rota_la_cookie(self):
        cliente = self._iniciar_sesion()
        antes = cliente.cookies[settings.REFRESH_TOKEN_COOKIE_NAME].value

        respuesta = cliente.post(reverse('token_refresh'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(set(respuesta.data), {'access'})
        self.assertNotEqual(respuesta.cookies[settings.REFRESH_TOKEN_COOKIE_NAME].value, antes)

    def test_refresh_con_token_ya_rotado_es_rechazado(self):
        cliente = self._iniciar_sesion()
        viejo = cliente.cookies[settings.REFRESH_TOKEN_COOKIE_NAME].value
        cliente.post(reverse('token_refresh'))

        atacante = APIClient()
        atacante.cookies[settings.REFRESH_TOKEN_COOKIE_NAME] = viejo
        self.assertEqual(atacante.post(reverse('token_refresh')).status_code, 400)

    def test_refresh_sin_cookie_es_400(self):
        self.assertEqual(APIClient().post(reverse('token_refresh')).status_code, 400)

    def test_refresh_de_usuario_desactivado_es_rechazado(self):
        cliente = self._iniciar_sesion()
        Usuario.objects.filter(pk=self.usuario.pk).update(estado='I')

        self.assertEqual(cliente.post(reverse('token_refresh')).status_code, 400)

    def test_logout_pone_el_token_en_lista_negra_y_limpia_la_cookie(self):
        cliente = self._iniciar_sesion()
        token = cliente.cookies[settings.REFRESH_TOKEN_COOKIE_NAME].value

        respuesta = cliente.post(reverse('logout'))

        self.assertEqual(respuesta.status_code, 204)
        self.assertEqual(respuesta.cookies[settings.REFRESH_TOKEN_COOKIE_NAME].value, '')
        reutilizado = APIClient()
        reutilizado.cookies[settings.REFRESH_TOKEN_COOKIE_NAME] = token
        self.assertEqual(reutilizado.post(reverse('token_refresh')).status_code, 400)

    def test_logout_sin_sesion_tambien_responde_204(self):
        self.assertEqual(APIClient().post(reverse('logout')).status_code, 204)
