import os
import shutil

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.configuracion.models import Comunicado, Imagen
from apps.core.testing import ApiTestCase, crear_usuario
from apps.documentos.models import Category, DocsEtiqueta, Etiqueta, EtiquetaRol, Upload

MEDIA = 'media_test_configuracion'


def _png(nombre='img.png') -> SimpleUploadedFile:
    return SimpleUploadedFile(nombre, b'\x89PNG\r\n\x1a\n', content_type='image/png')


@override_settings(MEDIA_ROOT=MEDIA)
class EscriturasSoloAdminTests(ApiTestCase):
    def tearDown(self):
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_un_usuario_normal_lee_pero_no_escribe(self):
        lecturas = ('configuracion-etiquetas', 'configuracion-imagenes', 'configuracion-comunicados', 'configuracion-actividades', 'configuracion-roles')
        for nombre in lecturas:
            self.assertEqual(self.cliente_usuario.get(reverse(nombre)).status_code, 200, nombre)

        escrituras = (
            ('configuracion-etiquetas', {'etiquetaNombre': 'X', 'rolesPermitidos': [1]}, 'json'),
            ('configuracion-imagenes', {'file': _png()}, 'multipart'),
            ('configuracion-comunicados', {'titulo': 't', 'contenido': 'c', 'file': _png()}, 'multipart'),
            ('configuracion-actividades', {'fecha': '2026-10-30', 'titulo': 'x'}, 'json'),
        )
        for nombre, datos, formato in escrituras:
            self.assertEqual(self.cliente_usuario.post(reverse(nombre), datos, format=formato).status_code, 403, nombre)

    def test_los_roles_dicen_que_permiten(self):
        roles = {rol['id']: rol for rol in self.cliente_usuario.get(reverse('configuracion-roles')).data}

        self.assertEqual(roles[3]['permisos'], ['financiero.aprobar', 'financiero.exportar', 'financiero.ver_todas'])
        self.assertEqual(roles[2]['permisos'], ['financiero.subir'])
        self.assertEqual(len(roles[1]['permisos']), 10)

    def test_un_usuario_normal_no_edita_ni_elimina(self):
        comunicado = Comunicado.objects.create(titulo='t', contenido='c', imagen='https://s3/x.png', usuario_sube='a', fecha_subida=timezone.localdate())
        etiqueta = Etiqueta.objects.create(etiqueta_nombre='E')

        self.assertEqual(self.cliente_usuario.delete(reverse('configuracion-comunicado-detail', args=[comunicado.id])).status_code, 403)
        self.assertEqual(self.cliente_usuario.delete(reverse('configuracion-etiqueta-detail', args=[etiqueta.id])).status_code, 403)


@override_settings(MEDIA_ROOT=MEDIA)
class CarruselTests(ApiTestCase):
    def tearDown(self):
        shutil.rmtree(MEDIA, ignore_errors=True)

    def _subir(self):
        return self.cliente_admin.post(reverse('configuracion-imagenes'), {'file': _png()}, format='multipart')

    def test_cada_imagen_nueva_toma_el_primer_puesto_libre(self):
        puestos = [self._subir().data['puesto'] for _ in range(3)]

        self.assertEqual(puestos, [1, 2, 3])

    def test_maximo_cuatro_imagenes(self):
        for _ in range(4):
            self.assertEqual(self._subir().status_code, 201)

        respuesta = self._subir()

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(Imagen.objects.count(), 4)

    def test_cambiar_de_puesto_intercambia_si_esta_ocupado(self):
        primera, segunda = self._subir().data, self._subir().data

        respuesta = self.cliente_admin.patch(reverse('configuracion-imagen-detail', args=[primera['id']]), {'puesto': 2}, format='json')

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Imagen.objects.get(pk=primera['id']).puesto, 2)
        self.assertEqual(Imagen.objects.get(pk=segunda['id']).puesto, 1)

    def test_puesto_fuera_de_rango_o_no_numerico(self):
        imagen = self._subir().data
        url = reverse('configuracion-imagen-detail', args=[imagen['id']])

        for valor in (0, 5, 'abc'):
            self.assertEqual(self.cliente_admin.patch(url, {'puesto': valor}, format='json').status_code, 400, valor)

    def test_eliminar_borra_el_archivo_local_pero_nunca_toca_urls_externas(self):
        local = self._subir().data
        archivo = os.path.join(MEDIA, local['ruta_img'].removeprefix('/media/'))
        externa = Imagen.objects.create(archivo='a.png', ruta_img='https://bucket.s3.amazonaws.com/imagenes/a.png', puesto=4, creado_en=timezone.now())
        self.assertTrue(os.path.exists(archivo))

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.cliente_admin.delete(reverse('configuracion-imagen-detail', args=[local['id']])).status_code, 204)
            self.assertEqual(self.cliente_admin.delete(reverse('configuracion-imagen-detail', args=[externa.id])).status_code, 204)

        self.assertFalse(os.path.exists(archivo))

    def test_imagen_inexistente_es_404(self):
        self.assertEqual(self.cliente_admin.delete(reverse('configuracion-imagen-detail', args=[999])).status_code, 404)


@override_settings(MEDIA_ROOT=MEDIA)
class ComunicadosYActividadesTests(ApiTestCase):
    def tearDown(self):
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_un_comunicado_nuevo_exige_imagen(self):
        respuesta = self.cliente_admin.post(reverse('configuracion-comunicados'), {'titulo': 't', 'contenido': 'c'}, format='multipart')

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['file'], ['Se requiere una imagen para publicar un comunicado nuevo.'])

    def test_publicar_y_editar(self):
        creado = self.cliente_admin.post(
            reverse('configuracion-comunicados'), {'titulo': 'Aviso', 'contenido': 'Texto', 'file': _png()}, format='multipart'
        )
        self.assertEqual(creado.status_code, 201)
        self.assertEqual(creado.data['usuario_sube'], self.admin.email)

        editado = self.cliente_admin.patch(
            reverse('configuracion-comunicado-detail', args=[creado.data['id']]), {'titulo': 'Aviso 2', 'contenido': 'Texto 2'}, format='multipart'
        )
        self.assertEqual(editado.status_code, 200)
        self.assertEqual(editado.data['titulo'], 'Aviso 2')

    def test_la_lista_cacheada_se_actualiza_al_publicar(self):
        self.assertEqual(self.cliente_usuario.get(reverse('configuracion-comunicados')).data, [])

        with self.captureOnCommitCallbacks(execute=True):
            self.cliente_admin.post(reverse('configuracion-comunicados'), {'titulo': 'Aviso', 'contenido': 'Texto', 'file': _png()}, format='multipart')

        self.assertEqual(len(self.cliente_usuario.get(reverse('configuracion-comunicados')).data), 1)

    def test_eliminar_comunicado_borra_su_imagen_local(self):
        creado = self.cliente_admin.post(
            reverse('configuracion-comunicados'), {'titulo': 'Aviso', 'contenido': 'Texto', 'file': _png()}, format='multipart'
        ).data
        archivo = os.path.join(MEDIA, creado['imagen'].removeprefix('/media/'))

        with self.captureOnCommitCallbacks(execute=True):
            self.cliente_admin.delete(reverse('configuracion-comunicado-detail', args=[creado['id']]))

        self.assertFalse(os.path.exists(archivo))

    def test_actividad_requiere_fecha_y_titulo_y_invalida_la_cache(self):
        self.assertEqual(self.cliente_admin.post(reverse('configuracion-actividades'), {'titulo': 'x'}, format='json').status_code, 400)
        self.assertEqual(self.cliente_usuario.get(reverse('configuracion-actividades')).data, [])

        with self.captureOnCommitCallbacks(execute=True):
            creada = self.cliente_admin.post(
                reverse('configuracion-actividades'), {'fecha': '2026-10-30', 'titulo': 'Capacitación', 'hora_desde': '10:00'}, format='json'
            )

        self.assertEqual(creada.status_code, 201)
        self.assertEqual(len(self.cliente_usuario.get(reverse('configuracion-actividades')).data), 1)

    def test_cumpleanos_del_mes_se_actualiza_cuando_un_admin_edita_al_usuario(self):
        cumple = crear_usuario(name='Cumple', fecha_nacimiento=timezone.localdate().replace(year=1990), email='cumple@inversa.hn')
        self.assertEqual([c['name'] for c in self.cliente_usuario.get(reverse('configuracion-cumpleanos')).data], ['Cumple'])

        with self.captureOnCommitCallbacks(execute=True):
            self.cliente_admin.patch(reverse('usuarios-detail', args=[cumple.pk]), {'name': 'Cumple Editado'}, format='json')

        self.assertEqual([c['name'] for c in self.cliente_usuario.get(reverse('configuracion-cumpleanos')).data], ['Cumple Editado'])

    def test_cumpleanos_del_mes_se_actualiza_cuando_el_usuario_edita_su_perfil(self):
        Usuario = type(self.usuario)
        Usuario.objects.filter(pk=self.usuario.pk).update(fecha_nacimiento=timezone.localdate().replace(year=1990))
        self.assertEqual(len(self.cliente_usuario.get(reverse('configuracion-cumpleanos')).data), 1)

        with self.captureOnCommitCallbacks(execute=True):
            self.cliente_usuario.patch(reverse('perfil'), {'name': 'Nombre Nuevo', 'phone_number': '1'}, format='json')

        self.assertEqual(self.cliente_usuario.get(reverse('configuracion-cumpleanos')).data[0]['name'], 'Nombre Nuevo')


class EtiquetasTests(ApiTestCase):
    def _guardar(self, **extra):
        datos = {'etiquetaNombre': 'General', 'rolesPermitidos': [1, 2], **extra}
        return self.cliente_admin.post(reverse('configuracion-etiquetas'), datos, format='json')

    def test_crear_y_editar_reemplaza_los_roles(self):
        creada = self._guardar()
        self.assertEqual(creada.status_code, 201)
        self.assertEqual(EtiquetaRol.objects.filter(etiqueta_id=creada.data['id']).count(), 2)

        self._guardar(id=creada.data['id'], rolesPermitidos=[1])

        self.assertEqual(EtiquetaRol.objects.filter(etiqueta_id=creada.data['id']).count(), 1)

    def test_una_etiqueta_no_puede_ser_su_propio_padre_ni_tener_un_padre_inexistente(self):
        creada = self._guardar().data

        self.assertEqual(self._guardar(id=creada['id'], parent_id=creada['id']).status_code, 400)
        self.assertEqual(self._guardar(parent_id=9999).status_code, 400)

    def test_no_se_elimina_con_hijas(self):
        padre = self._guardar().data
        self._guardar(etiquetaNombre='Hija', parent_id=padre['id'])

        respuesta = self.cliente_admin.delete(reverse('configuracion-etiqueta-detail', args=[padre['id']]))

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('hijas', respuesta.data['detail'])
        self.assertTrue(Etiqueta.objects.filter(pk=padre['id']).exists())

    def test_no_se_elimina_con_documentos_asociados(self):
        etiqueta = self._guardar().data
        categoria = Category.objects.create(name='C', description='d', created_at=timezone.now())
        documento = Upload.objects.create(fname='x', name='x', area=categoria, estado='Activo', fecha=timezone.now(), tipo='x', tamanio='1')
        DocsEtiqueta.objects.create(documento=documento, etiqueta_id=etiqueta['id'])

        respuesta = self.cliente_admin.delete(reverse('configuracion-etiqueta-detail', args=[etiqueta['id']]))

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('documentos', respuesta.data['detail'])

    def test_se_elimina_una_etiqueta_libre_y_se_invalida_la_cache(self):
        etiqueta = self._guardar().data
        self.assertEqual(len(self.cliente_usuario.get(reverse('configuracion-etiquetas')).data), 1)

        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.cliente_admin.delete(reverse('configuracion-etiqueta-detail', args=[etiqueta['id']]))

        self.assertEqual(respuesta.status_code, 204)
        self.assertEqual(self.cliente_usuario.get(reverse('configuracion-etiquetas')).data, [])
        self.assertFalse(EtiquetaRol.objects.filter(etiqueta_id=etiqueta['id']).exists())

    def test_etiqueta_inexistente_es_404(self):
        self.assertEqual(self.cliente_admin.delete(reverse('configuracion-etiqueta-detail', args=[999])).status_code, 404)
