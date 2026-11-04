from rest_framework.response import Response
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase

from apps.core.cache import cached, invalidar
from config.exception_handler import custom_exception_handler


class CacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.llamadas = 0

    def _cargador(self):
        self.llamadas += 1
        return {'valor': self.llamadas}

    def test_el_cargador_se_ejecuta_una_sola_vez(self):
        primero = cached('prueba:lista', 60, self._cargador)
        segundo = cached('prueba:lista', 60, self._cargador)

        self.assertEqual(primero, segundo)
        self.assertEqual(self.llamadas, 1)

    def test_invalidar_solo_actua_al_confirmar_la_transaccion(self):
        cached('prueba:lista', 60, self._cargador)

        with self.captureOnCommitCallbacks(execute=False) as pendientes:
            invalidar('prueba')
        cached('prueba:lista', 60, self._cargador)
        self.assertEqual(self.llamadas, 1)

        for callback in pendientes:
            callback()
        cached('prueba:lista', 60, self._cargador)
        self.assertEqual(self.llamadas, 2)

    def test_invalidar_un_espacio_no_afecta_a_otros(self):
        cached('uno:a', 60, self._cargador)
        cached('dos:a', 60, self._cargador)

        with self.captureOnCommitCallbacks(execute=True):
            invalidar('uno')
        cached('uno:a', 60, self._cargador)
        cached('dos:a', 60, self._cargador)

        self.assertEqual(self.llamadas, 3)

    def test_el_ttl_vence(self):
        cached('ttl:a', 60, self._cargador)
        cache.clear()  # equivale a expirar la entrada

        cached('ttl:a', 60, self._cargador)

        self.assertEqual(self.llamadas, 2)


def _manejar(excepcion: Exception) -> Response:
    respuesta = custom_exception_handler(excepcion, {})
    assert respuesta is not None, 'el manejador debe responder a esta excepción'
    return respuesta


class ManejadorDeExcepcionesTests(SimpleTestCase):
    def test_no_existe_es_404(self):
        respuesta = _manejar(ObjectDoesNotExist())

        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(respuesta.data['detail'], 'El registro solicitado no existe.')

    def test_validacion_de_django_sin_corchetes(self):
        simple = _manejar(DjangoValidationError('Ya existe.'))
        por_campo = _manejar(DjangoValidationError({'name': 'Ya existe.'}))

        self.assertEqual(simple.status_code, 400)
        self.assertEqual(simple.data, {'detail': 'Ya existe.'})
        self.assertEqual(por_campo.data['name'], ['Ya existe.'])

    def test_integridad_es_400(self):
        self.assertEqual(_manejar(IntegrityError()).status_code, 400)
