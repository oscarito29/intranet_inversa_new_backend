from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from rest_framework.test import APIClient

from config.settings.validaciones import exigir_clave_secreta


class ClaveSecretaTests(SimpleTestCase):
    def test_acepta_una_clave_larga_y_aleatoria(self):
        clave = 'aB3-xK9_pQ7zLm2WvT5nR8yU1cD4eF6gH0jI-sOkNbVxZaQwErTyUiOpAsDf'

        self.assertEqual(exigir_clave_secreta(clave), clave)

    def test_rechaza_las_claves_de_ejemplo(self):
        for clave in ('django-insecure-change-me-in-env', 'change-me', 'django-insecure-' + 'x' * 60):
            with self.subTest(clave=clave), self.assertRaises(ImproperlyConfigured):
                exigir_clave_secreta(clave)

    def test_rechaza_una_clave_corta_aunque_sea_aleatoria(self):
        with self.assertRaisesMessage(ImproperlyConfigured, '50 caracteres'):
            exigir_clave_secreta('aB3xK9pQ7zLm2WvT5nR8')

    def test_rechaza_una_clave_vacia(self):
        with self.assertRaises(ImproperlyConfigured):
            exigir_clave_secreta('')


class SuperficieExpuestaTests(SimpleTestCase):
    """Por defecto (producción y pruebas) no se publica ni Swagger ni el sitio /admin/ de Django."""

    def test_el_sitio_de_administracion_de_django_no_existe(self):
        self.assertEqual(APIClient().get('/admin/').status_code, 404)

    def test_la_documentacion_de_la_api_no_se_publica(self):
        self.assertEqual(APIClient().get('/api/v1/docs/').status_code, 404)
        self.assertEqual(APIClient().get('/api/v1/schema/').status_code, 404)
        for nombre in ('schema', 'swagger-ui'):
            with self.assertRaises(NoReverseMatch):
                reverse(nombre)
