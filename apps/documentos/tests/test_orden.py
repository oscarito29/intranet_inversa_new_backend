from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase

from .test_documentos import _categoria, _documento


class OrdenPorFechaTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        categoria = _categoria()
        ahora = timezone.now()
        for nombre, dias in (('medio.pdf', 5), ('viejo.pdf', 30), ('nuevo.pdf', 1)):
            documento = _documento(categoria, nombre=nombre)
            documento.fecha = ahora - timedelta(days=dias)
            documento.save()

    def _nombres(self, **parametros):
        return [d['name'] for d in self.cliente_usuario.get(reverse('documentos-documentos'), parametros).data['results']]

    def test_por_defecto_los_mas_recientes_primero(self):
        self.assertEqual(self._nombres(), ['nuevo.pdf', 'medio.pdf', 'viejo.pdf'])

    def test_los_mas_antiguos_primero(self):
        self.assertEqual(self._nombres(orden='antiguos'), ['viejo.pdf', 'medio.pdf', 'nuevo.pdf'])

    def test_el_orden_se_mantiene_entre_paginas(self):
        pagina1 = self._nombres(orden='antiguos', page_size=2, page=1)
        pagina2 = self._nombres(orden='antiguos', page_size=2, page=2)

        self.assertEqual(pagina1 + pagina2, ['viejo.pdf', 'medio.pdf', 'nuevo.pdf'])

    def test_un_orden_desconocido_es_400(self):
        self.assertEqual(self.cliente_usuario.get(reverse('documentos-documentos'), {'orden': 'azar'}).status_code, 400)
