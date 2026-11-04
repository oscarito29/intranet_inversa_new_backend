from unittest import mock

from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.core.testing import ApiTestCase
from apps.financial.models import Bitacora
from apps.usuarios import bloqueo

CLAVE_BUENA = 'Clave-segura-123'


def _login(correo: str, password: str, cliente: APIClient | None = None):
    return (cliente or APIClient()).post(reverse('token_obtain_pair'), {'email': correo, 'password': password}, format='json')


class BloqueoPorIntentosTests(ApiTestCase):
    def _fallar(self, veces: int, correo: str | None = None):
        return [_login(correo or self.usuario.email, 'incorrecta').status_code for _ in range(veces)]

    def test_los_primeros_intentos_fallidos_son_401(self):
        self.assertEqual(self._fallar(bloqueo.MAX_INTENTOS - 1), [401] * (bloqueo.MAX_INTENTOS - 1))

    def test_el_ultimo_intento_permitido_bloquea_con_429_y_dice_cuanto_esperar(self):
        codigos = self._fallar(bloqueo.MAX_INTENTOS)

        self.assertEqual(codigos[:-1], [401] * (bloqueo.MAX_INTENTOS - 1))
        respuesta = _login(self.usuario.email, 'incorrecta')
        self.assertEqual(codigos[-1], 429)
        self.assertEqual(respuesta.status_code, 429)
        self.assertIn('Demasiados intentos', respuesta.data['detail'])
        self.assertIn('15 minutos', respuesta.data['detail'])
        self.assertIn('Retry-After', respuesta)

    def test_bloqueado_ni_la_clave_correcta_entra(self):
        self._fallar(bloqueo.MAX_INTENTOS)

        self.assertEqual(_login(self.usuario.email, CLAVE_BUENA).status_code, 429)

    def test_el_bloqueo_es_solo_de_ese_correo(self):
        self._fallar(bloqueo.MAX_INTENTOS)

        self.assertEqual(_login(self.admin.email, CLAVE_BUENA).status_code, 200)

    def test_no_distingue_mayusculas_ni_espacios_en_el_correo(self):
        self._fallar(bloqueo.MAX_INTENTOS - 1)
        _login(f'  {self.usuario.email.upper()} ', 'incorrecta')

        self.assertEqual(_login(self.usuario.email, CLAVE_BUENA).status_code, 429)

    def test_un_correo_que_no_existe_se_bloquea_igual_para_no_revelar_cuales_existen(self):
        codigos = self._fallar(bloqueo.MAX_INTENTOS, correo='nadie@inversa.hn')

        self.assertEqual(codigos[-1], 429)

    def test_un_acceso_correcto_reinicia_la_cuenta(self):
        self._fallar(bloqueo.MAX_INTENTOS - 1)
        self.assertEqual(_login(self.usuario.email, CLAVE_BUENA).status_code, 200)

        self.assertEqual(self._fallar(bloqueo.MAX_INTENTOS - 1), [401] * (bloqueo.MAX_INTENTOS - 1))

    def test_pasado_el_tiempo_se_puede_volver_a_intentar(self):
        self._fallar(bloqueo.MAX_INTENTOS)
        with mock.patch.object(bloqueo.time, 'time', return_value=bloqueo.time.time() + bloqueo.BLOQUEO_SEGUNDOS + 5):
            self.assertEqual(bloqueo.segundos_de_bloqueo(self.usuario.email), 0)

    def test_el_bloqueo_queda_en_la_bitacora_una_sola_vez(self):
        self._fallar(bloqueo.MAX_INTENTOS)
        _login(self.usuario.email, 'incorrecta')

        self.assertEqual(Bitacora.objects.filter(accion='Bloqueo', usuario=self.usuario.email).count(), 1)

    def test_un_acceso_correcto_queda_en_la_bitacora(self):
        _login(self.usuario.email, CLAVE_BUENA)

        self.assertTrue(Bitacora.objects.filter(accion='Login', usuario=self.usuario.email).exists())

    def test_un_acceso_fallido_no_llena_la_bitacora(self):
        self._fallar(2)

        self.assertFalse(Bitacora.objects.filter(accion='Login').exists())

    def test_cerrar_sesion_queda_en_la_bitacora(self):
        cliente = APIClient()
        _login(self.usuario.email, CLAVE_BUENA, cliente)

        cliente.post(reverse('logout'))

        self.assertTrue(Bitacora.objects.filter(accion='Logout', usuario=self.usuario.email).exists())


class LimitePorDireccionTests(ApiTestCase):
    def test_demasiados_intentos_desde_la_misma_direccion_dan_429_en_espanol(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'login': '3/min'}):
            codigos = [_login(f'otro{numero}@inversa.hn', 'x').status_code for numero in range(5)]

        self.assertEqual(codigos[:3], [401, 401, 401])
        self.assertEqual(codigos[3:], [429, 429])

    def test_el_mensaje_del_limite_esta_en_espanol(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'login': '1/min'}):
            _login('a@inversa.hn', 'x')
            respuesta = _login('b@inversa.hn', 'x')

        self.assertEqual(respuesta.status_code, 429)
        self.assertTrue(respuesta.data['detail'].startswith('Demasiados intentos. Espera'))

    def test_cambiar_la_contrasena_tambien_tiene_limite(self):
        datos = {'actual': 'mala', 'nuevo': 'Otra-clave-segura-1', 'repetido': 'Otra-clave-segura-1'}
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'password': '2/min'}):
            codigos = [self.cliente_usuario.post(reverse('cambiar-password'), datos, format='json').status_code for _ in range(4)]

        self.assertEqual(codigos, [400, 400, 429, 429])
