import logging
import logging.config
import sys
from unittest import mock

from django.db import OperationalError
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.testing import ApiTestCase
from config.settings.observabilidad import configuracion_de_logs, iniciar_sentry


class SaludTests(ApiTestCase):
    def test_responde_sin_sesion_y_dice_que_todo_esta_bien(self):
        respuesta = APIClient().get(reverse('salud'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data, {'estado': 'ok', 'base_de_datos': 'ok', 'cache': 'ok'})

    def test_una_credencial_invalida_no_la_tumba(self):
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION='Bearer esto.no.es.un.token')

        self.assertEqual(cliente.get(reverse('salud')).status_code, 200)

    def test_si_la_base_no_responde_da_503_sin_filtrar_el_error(self):
        with mock.patch('apps.core.views.connection.cursor', side_effect=OperationalError('Access denied for user root@10.0.0.5')):
            with self.assertLogs('apps.core.views', level='ERROR'):
                respuesta = APIClient().get(reverse('salud'))

        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta.data['estado'], 'falla')
        self.assertEqual(respuesta.data['base_de_datos'], 'falla')
        self.assertNotIn('root', str(respuesta.data))
        self.assertNotIn('10.0.0.5', str(respuesta.data))

    def test_si_la_cache_no_responde_da_503(self):
        with mock.patch('apps.core.views.cache.set', side_effect=ConnectionError('redis caído')):
            with self.assertLogs('apps.core.views', level='ERROR'):
                respuesta = APIClient().get(reverse('salud'))

        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta.data['cache'], 'falla')
        self.assertEqual(respuesta.data['base_de_datos'], 'ok')

    def test_solo_se_puede_consultar(self):
        self.assertEqual(APIClient().post(reverse('salud')).status_code, 405)


class LogsTests(SimpleTestCase):
    def test_todo_va_a_la_salida_estandar_y_no_a_archivos(self):
        config = configuracion_de_logs('WARNING')

        self.assertEqual({h['class'] for h in config['handlers'].values()}, {'logging.StreamHandler'})
        self.assertEqual(config['root']['level'], 'WARNING')

    def test_las_consultas_sql_no_se_registran_ni_en_debug(self):
        config = configuracion_de_logs('DEBUG')

        self.assertEqual(config['loggers']['django.db.backends']['level'], 'WARNING')

    def test_la_configuracion_es_valida_para_logging(self):
        logging.config.dictConfig(configuracion_de_logs('INFO'))
        self.addCleanup(logging.config.dictConfig, configuracion_de_logs('INFO'))


class SentryTests(SimpleTestCase):
    def test_sin_dsn_no_conecta_ni_importa_el_sdk(self):
        with mock.patch.dict(sys.modules, {'sentry_sdk': None}):  # si lo intentara importar, fallaría
            self.assertFalse(iniciar_sentry('', 'production'))

    def test_con_dsn_no_envia_datos_personales_ni_el_cuerpo_de_las_peticiones(self):
        with mock.patch('sentry_sdk.init') as iniciar:
            self.assertTrue(iniciar_sentry('https://clave@o0.ingest.sentry.io/1', 'production', 'v1.2.3'))

        opciones = iniciar.call_args.kwargs
        self.assertFalse(opciones['send_default_pii'])
        self.assertEqual(opciones['max_request_body_size'], 'never')
        self.assertEqual((opciones['environment'], opciones['release']), ('production', 'v1.2.3'))


@override_settings(DEBUG=False)
class SettingsDeProduccionTests(SimpleTestCase):
    def test_el_balanceador_puede_consultar_la_salud_por_http_sin_redireccion(self):
        import importlib
        import os

        variables = {
            'DJANGO_SECRET_KEY': 'k' * 60 + '9Zq!xW',
            'DB_NAME': 'x', 'DB_USER': 'x', 'DB_PASSWORD': 'x', 'DB_HOST': 'x',
            'REDIS_URL': 'redis://localhost:6379/0',
        }
        with mock.patch.dict(os.environ, variables):
            produccion = importlib.import_module('config.settings.production')

        self.assertEqual(produccion.SECURE_REDIRECT_EXEMPT, [r'^api/v1/salud/$'])
        self.assertTrue(produccion.SECURE_SSL_REDIRECT)
