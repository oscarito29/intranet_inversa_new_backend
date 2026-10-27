import shutil

from django.test import override_settings
from django.urls import reverse

from apps.core.testing import ApiTestCase
from apps.documentos.models import Category, Upload

from .test_documentos import _categoria, _documento, _pdf


class ConteoDeCategoriasTests(ApiTestCase):
    def _lista(self, cliente=None):
        return (cliente or self.cliente_admin).get(reverse('documentos-categorias')).data

    def test_cada_categoria_trae_sus_documentos_vigentes(self):
        categoria = _categoria('Contabilidad')
        _documento(categoria, nombre='a.pdf')
        _documento(categoria, nombre='b.pdf')
        _documento(categoria, estado=Upload.REEMPLAZADO, nombre='c.pdf')

        fila = self._lista()[0]

        self.assertEqual(fila['documentos'], 2)

    def test_puede_eliminar_solo_si_no_tiene_ningun_documento(self):
        vacia = _categoria('Vacía')
        solo_reemplazados = _categoria('Antigua')
        _documento(solo_reemplazados, estado=Upload.REEMPLAZADO)

        filas = {fila['name']: fila for fila in self._lista()}

        self.assertTrue(filas['Vacía']['puede_eliminar'])
        self.assertFalse(filas['Antigua']['puede_eliminar'])
        self.assertEqual(filas['Antigua']['documentos'], 0)
        self.assertTrue(vacia.id)

    def test_el_conteo_se_actualiza_al_subir_un_documento(self):
        categoria = _categoria('RRHH')
        self.assertEqual(self._lista()[0]['documentos'], 0)

        with self.captureOnCommitCallbacks(execute=True):
            _documento(categoria)
            from apps.core.cache import invalidar

            invalidar('documentos')

        self.assertEqual(self._lista()[0]['documentos'], 1)

    def test_crear_y_editar_devuelven_el_conteo(self):
        creada = self.cliente_admin.post(reverse('documentos-categorias'), {'name': 'Nueva', 'description': 'x'}, format='json')

        self.assertEqual(creada.status_code, 201)
        self.assertEqual((creada.data['documentos'], creada.data['puede_eliminar']), (0, True))


class EstadoDeCategoriasTests(ApiTestCase):
    def _cambiar(self, categoria, estado, cliente=None):
        return (cliente or self.cliente_admin).patch(reverse('documentos-categoria-detalle', args=[categoria.id]), {'estado': estado}, format='json')

    def test_el_admin_desactiva_y_reactiva(self):
        categoria = _categoria()

        apagada = self._cambiar(categoria, 'Inactivo')
        encendida = self._cambiar(categoria, 'Activo')

        self.assertEqual((apagada.status_code, apagada.data['estado']), (200, 'Inactivo'))
        self.assertEqual(encendida.data['estado'], 'Activo')

    def test_solo_un_admin_cambia_el_estado(self):
        categoria = _categoria()

        self.assertEqual(self._cambiar(categoria, 'Inactivo', cliente=self.cliente_usuario).status_code, 403)
        categoria.refresh_from_db()
        self.assertEqual(categoria.estado, 'Activo')

    def test_un_estado_invalido_es_400(self):
        self.assertEqual(self._cambiar(_categoria(), 'Pausada').status_code, 400)

    def test_categoria_inexistente_es_404(self):
        self.assertEqual(self._cambiar(Category(id=999), 'Inactivo').status_code, 404)

    def test_el_cambio_se_refleja_en_la_lista_cacheada(self):
        categoria = _categoria()
        self.assertEqual(self.cliente_admin.get(reverse('documentos-categorias')).data[0]['estado'], 'Activo')

        with self.captureOnCommitCallbacks(execute=True):
            self._cambiar(categoria, 'Inactivo')

        self.assertEqual(self.cliente_admin.get(reverse('documentos-categorias')).data[0]['estado'], 'Inactivo')

    def test_el_cambio_queda_en_la_bitacora(self):
        from apps.financial.models import Bitacora

        categoria = _categoria('Contabilidad')
        self._cambiar(categoria, 'Inactivo')

        self.assertTrue(Bitacora.objects.filter(descripcion='Desactiva la categoria Contabilidad', usuario=self.admin.email).exists())


@override_settings(MEDIA_ROOT='media_test_documentos')
class SubidaEnCategoriaInactivaTests(ApiTestCase):
    def tearDown(self):
        shutil.rmtree('media_test_documentos', ignore_errors=True)

    def test_no_se_sube_a_una_categoria_inactiva(self):
        categoria = _categoria()
        categoria.estado = Category.INACTIVA
        categoria.save()

        respuesta = self.cliente_admin.post(
            reverse('documentos-documentos'), {'file': _pdf(), 'name': 'Doc', 'area': categoria.id}, format='multipart'
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('area', respuesta.data)
        self.assertEqual(Upload.objects.count(), 0)

    def test_al_reactivarla_si_se_sube(self):
        categoria = _categoria()
        categoria.estado = Category.INACTIVA
        categoria.save()
        self.cliente_admin.patch(reverse('documentos-categoria-detalle', args=[categoria.id]), {'estado': 'Activo'}, format='json')

        respuesta = self.cliente_admin.post(
            reverse('documentos-documentos'), {'file': _pdf(), 'name': 'Doc', 'area': categoria.id}, format='multipart'
        )

        self.assertEqual(respuesta.status_code, 201)
