import os
import shutil

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase
from apps.documentos.models import DocsEtiqueta, Etiqueta, EtiquetaRol, Upload

from .test_documentos import _categoria, _documento, _pdf


class ListaPaginadaTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.contabilidad = _categoria('Contabilidad')
        self.rrhh = _categoria('RRHH')
        self.general = Etiqueta.objects.create(etiqueta_nombre='General')
        self.interna = Etiqueta.objects.create(etiqueta_nombre='Interna')
        for etiqueta in (self.general, self.interna):
            EtiquetaRol.objects.create(etiqueta=etiqueta, rol_id=1)
            EtiquetaRol.objects.create(etiqueta=etiqueta, rol_id=2)

    def _lista(self, **parametros):
        respuesta = self.cliente_usuario.get(reverse('documentos-documentos'), parametros)
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        return respuesta.data

    def test_pagina_los_resultados(self):
        for numero in range(5):
            _documento(self.contabilidad, nombre=f'doc-{numero}.pdf')

        primera = self._lista(page_size=2)
        tercera = self._lista(page_size=2, page=3)

        self.assertEqual((primera['count'], primera['total_pages'], len(primera['results'])), (5, 3, 2))
        self.assertEqual((tercera['page'], len(tercera['results'])), (3, 1))

    def test_una_pagina_fuera_de_rango_devuelve_la_ultima(self):
        _documento(self.contabilidad)

        self.assertEqual(self._lista(page=99)['page'], 1)

    def test_solo_lista_los_vigentes(self):
        _documento(self.contabilidad, nombre='vigente.pdf')
        _documento(self.contabilidad, estado=Upload.REEMPLAZADO, nombre='viejo.pdf')

        self.assertEqual([d['name'] for d in self._lista()['results']], ['vigente.pdf'])

    def test_filtra_por_texto_y_por_categoria(self):
        _documento(self.contabilidad, nombre='Balance general.pdf')
        _documento(self.rrhh, nombre='Reglamento interno.pdf')

        self.assertEqual([d['name'] for d in self._lista(q='balance')['results']], ['Balance general.pdf'])
        self.assertEqual([d['name'] for d in self._lista(categoria=self.rrhh.id)['results']], ['Reglamento interno.pdf'])

    def test_filtra_por_etiquetas_y_exige_todas(self):
        ambas = _documento(self.contabilidad, nombre='ambas.pdf')
        solo_una = _documento(self.contabilidad, nombre='una.pdf')
        for etiqueta in (self.general, self.interna):
            DocsEtiqueta.objects.create(documento=ambas, etiqueta=etiqueta)
        DocsEtiqueta.objects.create(documento=solo_una, etiqueta=self.general)

        self.assertEqual({d['name'] for d in self._lista(etiquetas=str(self.general.id))['results']}, {'ambas.pdf', 'una.pdf'})
        self.assertEqual([d['name'] for d in self._lista(etiquetas=f'{self.general.id},{self.interna.id}')['results']], ['ambas.pdf'])

    def test_cuenta_por_categoria_sin_aplicar_el_filtro_de_categoria(self):
        _documento(self.contabilidad, nombre='a.pdf')
        _documento(self.contabilidad, nombre='b.pdf')
        _documento(self.rrhh, nombre='c.pdf')

        datos = self._lista(categoria=self.rrhh.id)

        self.assertEqual(datos['count'], 1)
        self.assertEqual(datos['categorias'], {self.contabilidad.id: 2, self.rrhh.id: 1})

    def test_cada_fila_trae_sus_etiquetas(self):
        documento = _documento(self.contabilidad)
        DocsEtiqueta.objects.create(documento=documento, etiqueta=self.general)

        self.assertEqual(self._lista()['results'][0]['etiquetas'], [self.general.id])

    def test_trae_las_versiones_que_reemplazo_de_la_mas_reciente_a_la_mas_antigua(self):
        v1 = _documento(self.contabilidad, estado=Upload.REEMPLAZADO, nombre='v1.pdf')
        v2 = _documento(self.contabilidad, estado=Upload.REEMPLAZADO, nombre='v2.pdf')
        v2.reemplaza_a = v1
        v2.save()
        v3 = _documento(self.contabilidad, nombre='v3.pdf')
        v3.reemplaza_a = v2
        v3.save()

        fila = self._lista()['results'][0]

        self.assertEqual(fila['name'], 'v3.pdf')
        self.assertEqual([v['name'] for v in fila['versiones']], ['v2.pdf', 'v1.pdf'])

    def test_una_cadena_con_ciclo_no_se_cuelga(self):
        a = _documento(self.contabilidad, nombre='a.pdf')
        b = _documento(self.contabilidad, nombre='b.pdf')
        a.reemplaza_a, b.reemplaza_a = b, a
        a.save()
        b.save()

        self.assertEqual(len(self._lista()['results']), 2)

    def test_parametros_invalidos_son_400(self):
        for parametros in ({'page_size': 500}, {'page': 0}, {'etiquetas': 'a,b'}, {'categoria': 'x'}):
            respuesta = self.cliente_usuario.get(reverse('documentos-documentos'), parametros)
            self.assertEqual(respuesta.status_code, 400, parametros)

    def test_la_paginacion_respeta_la_visibilidad_por_rol(self):
        restringida = Etiqueta.objects.create(etiqueta_nombre='Solo admin')
        EtiquetaRol.objects.create(etiqueta=restringida, rol_id=1)
        oculto = _documento(self.contabilidad, nombre='oculto.pdf')
        DocsEtiqueta.objects.create(documento=oculto, etiqueta=restringida)
        _documento(self.contabilidad, nombre='visible.pdf')

        usuario = self._lista()
        admin = self.cliente_admin.get(reverse('documentos-documentos')).data

        self.assertEqual(usuario['count'], 1)
        self.assertEqual(admin['count'], 2)


@override_settings(MEDIA_ROOT='media_test_documentos')
class ArchivosDeLaListaTests(ApiTestCase):
    def tearDown(self):
        shutil.rmtree('media_test_documentos', ignore_errors=True)

    def _fila(self, nombre):
        resultados = self.cliente_usuario.get(reverse('documentos-documentos')).data['results']
        return next(d for d in resultados if d['name'] == nombre)

    def _crear(self, fname, nombre):
        return Upload.objects.create(fname=fname, name=nombre, area=_categoria(), estado='Activo', fecha=timezone.now(), tipo='x', tamanio='1')

    def test_un_archivo_legado_que_falta_se_marca_no_disponible(self):
        self._crear('no-existe.pdf', 'fantasma')

        fila = self._fila('fantasma')

        self.assertFalse(fila['disponible'])
        self.assertEqual(fila['fname'], '/media/legacy-documentos/no-existe.pdf')

    def test_un_archivo_legado_que_existe_esta_disponible(self):
        carpeta = 'media_test_documentos/legacy-documentos'
        os.makedirs(carpeta, exist_ok=True)
        with open(f'{carpeta}/real.pdf', 'wb') as archivo:
            archivo.write(b'%PDF-1.4')
        self._crear('real.pdf', 'real')

        self.assertTrue(self._fila('real')['disponible'])

    def test_una_url_de_s3_se_da_por_disponible(self):
        self._crear('https://bucket.s3.amazonaws.com/a.pdf', 'nube')

        self.assertTrue(self._fila('nube')['disponible'])

    def test_un_documento_subido_ahora_conserva_su_url_y_esta_disponible(self):
        categoria = _categoria()
        subido = self.cliente_admin.post(
            reverse('documentos-documentos'), {'file': _pdf('nuevo.pdf'), 'name': 'Nuevo', 'area': categoria.id}, format='multipart'
        )
        self.assertEqual(subido.status_code, 201)

        fila = self._fila('Nuevo')

        self.assertTrue(fila['fname'].startswith('/media/documentos-institucionales/'))
        self.assertNotIn('legacy-documentos', fila['fname'])
        self.assertTrue(fila['disponible'])
