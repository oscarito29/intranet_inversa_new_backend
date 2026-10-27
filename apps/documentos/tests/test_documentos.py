import shutil
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase
from apps.documentos.models import Category, DocsEtiqueta, Etiqueta, EtiquetaRol, Upload


def _categoria(nombre='Contabilidad') -> Category:
    return Category.objects.create(name=nombre, description='Descripción', created_at=timezone.now())


def _documento(categoria: Category, estado=Upload.ACTIVO, nombre='doc.pdf') -> Upload:
    return Upload.objects.create(
        fname=f'/media/{nombre}', name=nombre, area=categoria, estado=estado, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB'
    )


def _pdf(nombre='doc.pdf') -> SimpleUploadedFile:
    return SimpleUploadedFile(nombre, b'%PDF-1.4', content_type='application/pdf')


class CategoriasTests(ApiTestCase):
    def test_solo_un_admin_crea_edita_o_elimina(self):
        categoria = _categoria()
        datos = {'name': 'Nueva', 'description': 'x'}

        self.assertEqual(self.cliente_usuario.post(reverse('documentos-categorias'), datos, format='json').status_code, 403)
        self.assertEqual(self.cliente_usuario.put(reverse('documentos-categoria-detalle', args=[categoria.id]), datos, format='json').status_code, 403)
        self.assertEqual(self.cliente_usuario.delete(reverse('documentos-categoria-detalle', args=[categoria.id])).status_code, 403)

    def test_cualquier_usuario_lista(self):
        _categoria()

        self.assertEqual(len(self.cliente_usuario.get(reverse('documentos-categorias')).data), 1)

    def test_crear_y_editar_con_bitacora(self):
        creada = self.cliente_admin.post(reverse('documentos-categorias'), {'name': 'RRHH', 'description': 'x'}, format='json')
        self.assertEqual(creada.status_code, 201)

        editada = self.cliente_admin.put(
            reverse('documentos-categoria-detalle', args=[creada.data['id']]), {'name': 'RRHH 2', 'description': 'y'}, format='json'
        )
        self.assertEqual(editada.status_code, 200)
        self.assertEqual(editada.data['name'], 'RRHH 2')

    def test_nombre_duplicado_responde_sin_corchetes(self):
        _categoria('RRHH')

        respuesta = self.cliente_admin.post(reverse('documentos-categorias'), {'name': 'rrhh', 'description': 'x'}, format='json')

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['name'], ['Ya existe una categoría con ese nombre.'])
        self.assertNotIn('[', str(respuesta.data['name'][0]))

    def test_categoria_inexistente_es_404(self):
        self.assertEqual(self.cliente_admin.delete(reverse('documentos-categoria-detalle', args=[999])).status_code, 404)

    def test_no_se_elimina_con_documentos_de_ningun_estado(self):
        for estado in (Upload.ACTIVO, 'E', Upload.REEMPLAZADO):
            categoria = _categoria(f'Cat {estado}')
            _documento(categoria, estado=estado)

            respuesta = self.cliente_admin.delete(reverse('documentos-categoria-detalle', args=[categoria.id]))

            self.assertEqual(respuesta.status_code, 400, estado)
            self.assertTrue(Category.objects.filter(pk=categoria.id).exists())

    def test_se_elimina_una_categoria_vacia(self):
        categoria = _categoria()

        self.assertEqual(self.cliente_admin.delete(reverse('documentos-categoria-detalle', args=[categoria.id])).status_code, 204)

    def test_la_lista_cacheada_se_actualiza_al_guardar(self):
        self.assertEqual(self.cliente_usuario.get(reverse('documentos-categorias')).data, [])

        with self.captureOnCommitCallbacks(execute=True):
            self.cliente_admin.post(reverse('documentos-categorias'), {'name': 'Nueva', 'description': 'x'}, format='json')

        self.assertEqual(len(self.cliente_usuario.get(reverse('documentos-categorias')).data), 1)

    def test_la_segunda_lectura_no_consulta_la_base(self):
        self.cliente_usuario.get(reverse('documentos-categorias'))

        with self.assertNumQueries(0):
            self.cliente_usuario.get(reverse('documentos-categorias'))


@override_settings(MEDIA_ROOT='media_test_documentos')
class DocumentosTests(ApiTestCase):
    def tearDown(self):
        shutil.rmtree('media_test_documentos', ignore_errors=True)

    def _subir(self, categoria, cliente=None, **extra):
        datos = {'file': _pdf(), 'name': 'Reglamento', 'area': categoria.id, **extra}
        return (cliente or self.cliente_admin).post(reverse('documentos-documentos'), datos, format='multipart')

    def test_solo_un_admin_sube_documentos(self):
        respuesta = self._subir(_categoria(), cliente=self.cliente_usuario)

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(Upload.objects.count(), 0)

    def test_subir_con_etiquetas(self):
        categoria = _categoria()
        etiquetas = [Etiqueta.objects.create(etiqueta_nombre=n) for n in ('General', 'Prueba')]

        respuesta = self._subir(categoria, tagIds=[e.id for e in etiquetas])

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(DocsEtiqueta.objects.filter(documento_id=respuesta.data['id']).count(), 2)
        self.assertEqual(respuesta.data['estado'], Upload.ACTIVO)

    def test_categoria_inexistente_o_nombre_vacio_son_400(self):
        categoria = _categoria()

        self.assertIn('area', self._subir(Category(id=999)).data)
        self.assertEqual(self._subir(categoria, name='').status_code, 400)

    def test_etiqueta_inexistente_es_400(self):
        self.assertEqual(self._subir(_categoria(), tagIds=[12345]).status_code, 400)

    def test_solo_un_admin_reemplaza(self):
        categoria = _categoria()
        original = _documento(categoria)

        respuesta = self.cliente_usuario.post(
            reverse('documentos-reemplazar', args=[original.id]), {'file': _pdf(), 'name': 'v2', 'area': categoria.id}, format='multipart'
        )

        self.assertEqual(respuesta.status_code, 403)

    def test_reemplazar_versiona_y_marca_el_original(self):
        categoria = _categoria()
        original = _documento(categoria)

        respuesta = self.cliente_admin.post(
            reverse('documentos-reemplazar', args=[original.id]), {'file': _pdf('v2.pdf'), 'name': 'v2', 'area': categoria.id}, format='multipart'
        )

        self.assertEqual(respuesta.status_code, 201)
        original.refresh_from_db()
        self.assertEqual(original.estado, Upload.REEMPLAZADO)
        self.assertEqual(respuesta.data['reemplaza_a'], original.id)

    def test_no_se_reemplaza_dos_veces_el_mismo_documento(self):
        categoria = _categoria()
        original = _documento(categoria, estado=Upload.REEMPLAZADO)

        respuesta = self.cliente_admin.post(
            reverse('documentos-reemplazar', args=[original.id]), {'file': _pdf(), 'name': 'v3', 'area': categoria.id}, format='multipart'
        )

        self.assertEqual(respuesta.status_code, 400)

    def test_si_falla_a_mitad_del_reemplazo_no_queda_nada_a_medias(self):
        categoria = _categoria()
        original = _documento(categoria)
        antes = Upload.objects.count()

        with mock.patch('apps.documentos.services.registrar_bitacora', side_effect=RuntimeError('falla simulada')):
            with self.assertRaises(RuntimeError):
                self.cliente_admin.post(
                    reverse('documentos-reemplazar', args=[original.id]),
                    {'file': _pdf('v2.pdf'), 'name': 'v2', 'area': categoria.id},
                    format='multipart',
                )

        original.refresh_from_db()
        self.assertEqual(original.estado, Upload.ACTIVO)
        self.assertEqual(Upload.objects.count(), antes)

    def test_documento_original_inexistente_es_404(self):
        categoria = _categoria()

        respuesta = self.cliente_admin.post(
            reverse('documentos-reemplazar', args=[999]), {'file': _pdf(), 'name': 'v2', 'area': categoria.id}, format='multipart'
        )

        self.assertEqual(respuesta.status_code, 404)

    def test_url_de_archivos_legados_lleva_el_prefijo_media(self):
        categoria = _categoria()
        Upload.objects.create(
            fname='20220901_Reglamento.pdf', name='Reglamento', area=categoria, estado='E', fecha=timezone.now(), tipo='x', tamanio='1'
        )
        Upload.objects.create(
            fname='https://bucket.s3.amazonaws.com/a.pdf', name='A', area=categoria, estado='Activo', fecha=timezone.now(), tipo='x', tamanio='1'
        )

        urls = {d['name']: d['fname'] for d in self.cliente_usuario.get(reverse('documentos-documentos')).data['results']}

        self.assertEqual(urls['Reglamento'], '/media/legacy-documentos/20220901_Reglamento.pdf')
        self.assertEqual(urls['A'], 'https://bucket.s3.amazonaws.com/a.pdf')

    def test_mapa_docs_etiquetas_refleja_un_documento_nuevo(self):
        categoria = _categoria()
        etiqueta = Etiqueta.objects.create(etiqueta_nombre='General')
        self.assertEqual(self.cliente_admin.get(reverse('documentos-docs-etiquetas')).data, {})

        nuevo = self._subir(categoria, tagIds=[etiqueta.id])

        self.assertEqual(self.cliente_admin.get(reverse('documentos-docs-etiquetas')).data, {nuevo.data['id']: [etiqueta.id]})


class VisibilidadPorEtiquetaTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.categoria = _categoria()
        self.etiqueta_publica = Etiqueta.objects.create(etiqueta_nombre='Publica')
        self.etiqueta_admin = Etiqueta.objects.create(etiqueta_nombre='Solo admin')
        EtiquetaRol.objects.create(etiqueta=self.etiqueta_publica, rol_id=1)
        EtiquetaRol.objects.create(etiqueta=self.etiqueta_publica, rol_id=2)
        EtiquetaRol.objects.create(etiqueta=self.etiqueta_admin, rol_id=1)

        self.sin_etiquetas = _documento(self.categoria, nombre='sin-etiquetas.pdf')
        self.publico = _documento(self.categoria, nombre='publico.pdf')
        self.restringido = _documento(self.categoria, nombre='restringido.pdf')
        self.mixto = _documento(self.categoria, nombre='mixto.pdf')
        DocsEtiqueta.objects.create(documento=self.publico, etiqueta=self.etiqueta_publica)
        DocsEtiqueta.objects.create(documento=self.restringido, etiqueta=self.etiqueta_admin)
        DocsEtiqueta.objects.create(documento=self.mixto, etiqueta=self.etiqueta_admin)
        DocsEtiqueta.objects.create(documento=self.mixto, etiqueta=self.etiqueta_publica)

    def _nombres(self, cliente) -> set[str]:
        return {d['name'] for d in cliente.get(reverse('documentos-documentos')).data['results']}

    def test_el_admin_ve_todos(self):
        self.assertEqual(self._nombres(self.cliente_admin), {'sin-etiquetas.pdf', 'publico.pdf', 'restringido.pdf', 'mixto.pdf'})

    def test_un_usuario_ve_los_sin_etiquetas_y_los_de_una_etiqueta_permitida(self):
        self.assertEqual(self._nombres(self.cliente_usuario), {'sin-etiquetas.pdf', 'publico.pdf', 'mixto.pdf'})

    def test_el_mapa_de_etiquetas_solo_incluye_documentos_visibles(self):
        mapa = self.cliente_usuario.get(reverse('documentos-docs-etiquetas')).data

        self.assertNotIn(self.restringido.id, mapa)
        self.assertIn(self.publico.id, mapa)
        self.assertIn(self.mixto.id, mapa)

    def test_cambiar_los_roles_de_una_etiqueta_cambia_lo_que_ve_el_usuario(self):
        EtiquetaRol.objects.create(etiqueta=self.etiqueta_admin, rol_id=2)

        self.assertIn('restringido.pdf', self._nombres(self.cliente_usuario))
