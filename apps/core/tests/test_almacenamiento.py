import io
import os
import urllib.parse
from io import StringIO
from unittest import mock

import environ
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.configuracion.models import Imagen
from apps.core.archivos import PREFIJO_STORAGE, archivo_local_disponible, borrar_archivo, guardar_archivo, url_de_valor
from apps.core.campos import ArchivoUrlField
from apps.core.testing import ApiTestCase
from apps.documentos.models import Upload
from apps.documentos.tests.test_documentos import _categoria
from apps.financial.models import Documento
from apps.core.management.commands.migrar_archivos_legados import clave_en_bucket
from config.settings.almacenamiento import EXPIRACION_POR_DEFECTO_SEGUNDOS, opciones_s3, storages_con_s3

PDF = b'%PDF-1.4 contenido'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16

# Un storage en memoria que responde como un bucket: la dirección sale de la clave y no se guarda en la base.
STORAGE_EN_MEMORIA = {
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage', 'OPTIONS': {'base_url': 'https://archivos.test/'}},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(STORAGES=STORAGE_EN_MEMORIA)
class ValorGuardadoTests(SimpleTestCase):
    def test_se_guarda_la_clave_con_prefijo_y_no_la_direccion(self):
        valor = guardar_archivo('documentos/001/a.pdf', ContentFile(PDF, name='a.pdf'))

        self.assertEqual(valor, f'{PREFIJO_STORAGE}documentos/001/a.pdf')
        self.assertTrue(default_storage.exists('documentos/001/a.pdf'))

    def test_la_direccion_se_calcula_al_responder_con_el_storage_actual(self):
        self.assertEqual(url_de_valor('storage:documentos/001/a.pdf'), 'https://archivos.test/documentos/001/a.pdf')

    def test_lo_que_ya_es_una_direccion_se_entrega_tal_cual(self):
        for valor in ('https://bucket-viejo.s3.amazonaws.com/documentos/a.pdf', '/media/documentos/a.pdf', 'sin-formato.pdf'):
            self.assertEqual(url_de_valor(valor), valor)

    def test_vacio_o_nulo_se_conservan(self):
        self.assertIsNone(url_de_valor(None))
        self.assertEqual(url_de_valor(''), '')

    def test_un_archivo_con_nombre_repetido_no_pisa_al_anterior(self):
        uno = guardar_archivo('docs/a.pdf', ContentFile(b'1', name='a.pdf'))
        otro = guardar_archivo('docs/a.pdf', ContentFile(b'2', name='a.pdf'))

        self.assertNotEqual(uno, otro)

    def test_disponible_se_comprueba_en_el_storage(self):
        guardar_archivo('docs/existe.pdf', ContentFile(PDF, name='existe.pdf'))

        self.assertTrue(archivo_local_disponible('storage:docs/existe.pdf'))
        self.assertFalse(archivo_local_disponible('storage:docs/no-existe.pdf'))
        self.assertFalse(archivo_local_disponible(None))
        self.assertFalse(archivo_local_disponible(''))

    def test_el_campo_de_serializer_muestra_la_direccion(self):
        campo = ArchivoUrlField()

        self.assertEqual(campo.to_representation('storage:a/b.png'), 'https://archivos.test/a/b.png')
        self.assertTrue(campo.read_only)


@override_settings(STORAGES=STORAGE_EN_MEMORIA)
class BorrarArchivoTests(ApiTestCase):
    def test_borra_el_archivo_de_un_valor_storage_al_confirmar_la_transaccion(self):
        valor = guardar_archivo('docs/borrar.pdf', ContentFile(PDF, name='borrar.pdf'))

        with self.captureOnCommitCallbacks(execute=True):
            borrar_archivo(valor)

        self.assertFalse(default_storage.exists('docs/borrar.pdf'))

    def test_no_borra_hasta_confirmar(self):
        valor = guardar_archivo('docs/espera.pdf', ContentFile(PDF, name='espera.pdf'))

        with self.captureOnCommitCallbacks(execute=False):
            borrar_archivo(valor)

        self.assertTrue(default_storage.exists('docs/espera.pdf'))

    def test_las_direcciones_del_bucket_viejo_nunca_se_tocan(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            borrar_archivo('https://bucket-viejo.s3.amazonaws.com/documentos/a.pdf')

        self.assertEqual(callbacks, [])

    def test_una_clave_con_subida_de_directorio_se_ignora(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            borrar_archivo('storage:../../etc/passwd')
            borrar_archivo('storage:')

        self.assertEqual(callbacks, [])

    def test_nulo_no_hace_nada(self):
        borrar_archivo(None)


@override_settings(STORAGES=STORAGE_EN_MEMORIA)
class SubidasGuardanLaClaveTests(ApiTestCase):
    """Cada vía de subida guarda `storage:<clave>` en la base y responde con la dirección resuelta."""

    def test_documento_institucional(self):
        categoria = _categoria()
        datos = {'name': 'Balance', 'area': categoria.id, 'file': SimpleUploadedFile('balance.pdf', PDF)}

        self.cliente_admin.post(reverse('documentos-documentos'), datos, format='multipart')

        guardado = Upload.objects.get(name='Balance')
        self.assertTrue(guardado.fname.startswith('storage:documentos-institucionales/'))
        listado = self.cliente_admin.get(reverse('documentos-documentos')).data['results'][0]
        self.assertTrue(listado['fname'].startswith('https://archivos.test/documentos-institucionales/'))
        self.assertTrue(listado['disponible'])

    def test_estado_financiero(self):
        from datetime import timedelta

        from apps.financial.models import RangoFecha

        hoy = timezone.localdate()
        RangoFecha.objects.create(desde=hoy - timedelta(days=1), hasta=hoy + timedelta(days=1), email_usuario='a@inversa.hn', fecha_modifica=timezone.now())
        datos = {'file': SimpleUploadedFile('estado.pdf', PDF), 'anio': 2026, 'mes_id': 10, 'corporacion_id': '001', 'financiera_id': '001'}

        respuesta = self.cliente_usuario.post(reverse('financiero-documentos'), datos, format='multipart')

        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertTrue((Documento.objects.get().ruta_archivo or '').startswith('storage:documentos/001/001/2026/10/'))
        self.assertTrue(respuesta.data['ruta_archivo'].startswith('https://archivos.test/documentos/001/001/2026/10/'))

    def test_imagen_del_carrusel(self):
        respuesta = self.cliente_admin.post(reverse('configuracion-imagenes'), {'file': SimpleUploadedFile('a.png', PNG)}, format='multipart')

        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertTrue((Imagen.objects.get().ruta_img or '').startswith('storage:imagenes-carrusel/'))
        self.assertTrue(respuesta.data['ruta_img'].startswith('https://archivos.test/imagenes-carrusel/'))

    def test_foto_de_perfil(self):
        respuesta = self.cliente_usuario.post(reverse('perfil-foto'), {'picture': SimpleUploadedFile('foto.png', PNG)}, format='multipart')

        self.assertEqual(respuesta.status_code, 200)
        self.usuario.refresh_from_db()
        self.assertTrue((self.usuario.picture or '').startswith('storage:perfiles/'))
        self.assertTrue(respuesta.data['picture'].startswith('https://archivos.test/perfiles/'))
        self.assertTrue(self.cliente_usuario.get(reverse('me')).data['picture'].startswith('https://archivos.test/perfiles/'))

    def test_cambiar_la_foto_borra_la_anterior_del_storage(self):
        self.cliente_usuario.post(reverse('perfil-foto'), {'picture': SimpleUploadedFile('uno.png', PNG)}, format='multipart')
        self.usuario.refresh_from_db()
        anterior = (self.usuario.picture or '').removeprefix(PREFIJO_STORAGE)

        with self.captureOnCommitCallbacks(execute=True):
            self.cliente_usuario.post(reverse('perfil-foto'), {'picture': SimpleUploadedFile('dos.png', PNG)}, format='multipart')

        self.assertFalse(default_storage.exists(anterior))

    def test_el_directorio_muestra_la_foto_como_direccion(self):
        self.cliente_usuario.post(reverse('perfil-foto'), {'picture': SimpleUploadedFile('foto.png', PNG)}, format='multipart')

        personas = {p['email']: p for p in self.cliente_admin.get(reverse('usuarios-directorio')).data['personas']}

        self.assertTrue(personas[self.usuario.email]['foto'].startswith('https://archivos.test/perfiles/'))


class OpcionesS3Tests(SimpleTestCase):
    def _env(self, **variables) -> environ.Env:
        entorno = environ.Env()
        patcher = mock.patch.dict(os.environ, variables, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        for nombre in ('AWS_STORAGE_BUCKET_NAME', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'S3_URL_EXPIRA_SEGUNDOS', 'AWS_S3_REGION_NAME'):
            if nombre not in variables:
                self.addCleanup(os.environ.pop, nombre, None)
                os.environ.pop(nombre, None)
        return entorno

    def _opciones(self, **variables) -> dict:
        opciones = opciones_s3(self._env(**variables))
        assert opciones is not None, 'con bucket configurado debe haber opciones de S3'
        return opciones

    def test_sin_bucket_se_queda_el_disco(self):
        self.assertIsNone(opciones_s3(self._env()))

    def test_el_bucket_es_privado_y_las_direcciones_vencen(self):
        opciones = self._opciones(AWS_STORAGE_BUCKET_NAME='mi-bucket')

        self.assertEqual(opciones['bucket_name'], 'mi-bucket')
        self.assertTrue(opciones['querystring_auth'])
        self.assertEqual(opciones['querystring_expire'], EXPIRACION_POR_DEFECTO_SEGUNDOS)
        self.assertEqual(opciones['signature_version'], 's3v4')
        self.assertIsNone(opciones['default_acl'])  # ningún archivo se publica con permisos propios
        self.assertFalse(opciones['file_overwrite'])  # un archivo nuevo nunca pisa a uno existente

    def test_sin_claves_usa_el_rol_de_la_maquina(self):
        opciones = self._opciones(AWS_STORAGE_BUCKET_NAME='mi-bucket')

        self.assertNotIn('access_key', opciones)
        self.assertNotIn('secret_key', opciones)

    def test_con_las_dos_claves_las_usa(self):
        opciones = self._opciones(AWS_STORAGE_BUCKET_NAME='b', AWS_ACCESS_KEY_ID='AK', AWS_SECRET_ACCESS_KEY='SK')

        self.assertEqual((opciones['access_key'], opciones['secret_key']), ('AK', 'SK'))

    def test_una_clave_sin_su_pareja_es_un_error(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'van juntas'):
            opciones_s3(self._env(AWS_STORAGE_BUCKET_NAME='b', AWS_ACCESS_KEY_ID='AK'))

    def test_la_expiracion_y_la_region_se_pueden_cambiar(self):
        opciones = self._opciones(AWS_STORAGE_BUCKET_NAME='b', S3_URL_EXPIRA_SEGUNDOS='600', AWS_S3_REGION_NAME='us-east-2')

        self.assertEqual((opciones['querystring_expire'], opciones['region_name']), (600, 'us-east-2'))

    def test_la_direccion_real_de_s3_va_firmada_y_con_vencimiento(self):
        from storages.backends.s3 import S3Storage

        opciones = self._opciones(AWS_STORAGE_BUCKET_NAME='mi-bucket', AWS_ACCESS_KEY_ID='AKIAEJEMPLOEJEMPLO0', AWS_SECRET_ACCESS_KEY='secreta-de-ejemplo', S3_URL_EXPIRA_SEGUNDOS='900')
        storage = S3Storage(**opciones)

        url = storage.url('documentos/001/a.pdf')
        consulta = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)

        self.assertTrue(url.startswith('https://mi-bucket.s3.amazonaws.com/documentos/001/a.pdf?'))
        self.assertEqual(consulta['X-Amz-Expires'], ['900'])
        self.assertIn('X-Amz-Signature', consulta)

    def test_el_storage_de_produccion_es_s3_y_conserva_los_estaticos(self):
        configurado = storages_con_s3({'bucket_name': 'b'})

        self.assertEqual(configurado['default']['BACKEND'], 'storages.backends.s3.S3Storage')
        self.assertIn('staticfiles', configurado)


@override_settings(STORAGES=STORAGE_EN_MEMORIA)
class MigrarArchivosLegadosTests(ApiTestCase):
    HOST_VIEJO = 'bucket-viejo.s3.amazonaws.com'

    def setUp(self):
        super().setUp()
        self.categoria = _categoria()
        self.url = f'https://{self.HOST_VIEJO}/documentos/balance%202025.pdf'
        self.documento = Upload.objects.create(fname=self.url, name='Balance', area=self.categoria, estado=Upload.ACTIVO, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB')

    def _correr(self, *argumentos, contenido: bytes = PDF) -> str:
        salida = StringIO()
        respuesta = mock.MagicMock()
        respuesta.__enter__.return_value.read.return_value = contenido
        with mock.patch('apps.core.management.commands.migrar_archivos_legados.urllib.request.urlopen', return_value=respuesta) as abrir:
            call_command('migrar_archivos_legados', *argumentos, stdout=salida, stderr=salida)
        self.abrir = abrir
        return salida.getvalue()

    def test_el_ensayo_lista_lo_que_haria_y_no_descarga_ni_cambia_nada(self):
        texto = self._correr()

        self.assertIn('1 archivo(s) a migrar', texto)
        self.assertIn(self.url, texto)
        self.assertIn('Ensayo', texto)
        self.abrir.assert_not_called()
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.fname, self.url)

    def test_aplicar_descarga_sube_y_deja_la_clave_en_la_base(self):
        self._correr('--aplicar')

        self.documento.refresh_from_db()
        self.assertEqual(self.documento.fname, 'storage:legado/documentos-institucionales/' + f'{self.documento.pk}_balance_2025.pdf')
        self.assertTrue(default_storage.exists(self.documento.fname.removeprefix(PREFIJO_STORAGE)))
        self.abrir.assert_called_once()

    def test_el_documento_migrado_se_sirve_desde_el_storage_nuevo(self):
        self._correr('--aplicar')

        listado = self.cliente_admin.get(reverse('documentos-documentos')).data['results'][0]

        self.assertTrue(listado['fname'].startswith('https://archivos.test/legado/documentos-institucionales/'))

    def test_lo_que_no_es_del_formato_que_dice_no_entra(self):
        texto = self._correr('--aplicar', contenido=b'<html>no soy un pdf</html>')

        self.assertIn('falló', texto)
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.fname, self.url)

    def test_repetirlo_no_vuelve_a_migrar_lo_ya_migrado(self):
        self._correr('--aplicar')
        self._correr('--aplicar')

        self.abrir.assert_not_called()

    def test_origen_limita_a_ese_servidor(self):
        otro = Upload.objects.create(fname='https://otro-servidor.com/a.pdf', name='Otro', area=self.categoria, estado=Upload.ACTIVO, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB')

        self._correr('--aplicar', '--origen', self.HOST_VIEJO)

        otro.refresh_from_db()
        self.assertEqual(otro.fname, 'https://otro-servidor.com/a.pdf')
        self.assertEqual(self.abrir.call_count, 1)

    def test_ignora_las_rutas_locales_y_los_nombres_sueltos(self):
        Upload.objects.create(fname='/media/documentos/a.pdf', name='Local', area=self.categoria, estado=Upload.ACTIVO, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB')
        Upload.objects.create(fname='suelto.pdf', name='Suelto', area=self.categoria, estado=Upload.ACTIVO, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB')

        texto = self._correr()

        self.assertIn('1 archivo(s) a migrar', texto)

    def test_un_fallo_de_red_deja_la_fila_igual_y_sigue_con_las_demas(self):
        segundo = Upload.objects.create(fname=f'https://{self.HOST_VIEJO}/documentos/otro.pdf', name='Otro', area=self.categoria, estado=Upload.ACTIVO, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB')
        bueno = mock.MagicMock()
        bueno.__enter__.return_value.read.return_value = PDF
        salida = StringIO()

        with mock.patch('apps.core.management.commands.migrar_archivos_legados.urllib.request.urlopen', side_effect=[OSError('sin red'), bueno]):
            call_command('migrar_archivos_legados', '--aplicar', stdout=salida, stderr=salida)

        self.documento.refresh_from_db()
        segundo.refresh_from_db()
        self.assertEqual(self.documento.fname, self.url)
        self.assertTrue(segundo.fname.startswith('storage:'))
        self.assertIn('Fallidos: 1', salida.getvalue())

    def test_limite_acota_los_archivos_por_tabla(self):
        for numero in range(3):
            Upload.objects.create(fname=f'https://{self.HOST_VIEJO}/documentos/{numero}.pdf', name=f'D{numero}', area=self.categoria, estado=Upload.ACTIVO, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB')

        texto = self._correr('--limite', '2')

        self.assertIn('2 archivo(s) a migrar', texto)

    def test_tambien_migra_la_foto_de_perfil_y_las_imagenes_de_comunicados(self):
        from apps.configuracion.models import Comunicado
        from apps.usuarios.models import Usuario

        Usuario.objects.filter(pk=self.usuario.pk).update(picture=f'https://{self.HOST_VIEJO}/perfiles/foto.png')
        Comunicado.objects.create(titulo='t', contenido='c', imagen=f'https://{self.HOST_VIEJO}/comunicados/a.png', usuario_sube='a@inversa.hn', fecha_subida=timezone.localdate())

        self._correr('--aplicar', contenido=PNG)

        self.usuario.refresh_from_db()
        self.assertTrue((self.usuario.picture or '').startswith('storage:legado/perfiles/'))
        self.assertTrue(Comunicado.objects.get().imagen.startswith('storage:legado/comunicados/'))
        self.assertFalse(io.BytesIO(b'').closed)  # ancla para que el import de io no sobre


class ClaveEnBucketTests(SimpleTestCase):
    def test_reconoce_las_formas_de_url_de_s3(self):
        casos = {
            'https://inversa-intranet.s3.amazonaws.com/imagenes/user.png': 'imagenes/user.png',
            'https://inversa-intranet.s3.us-east-2.amazonaws.com/documentos/a%20b.pdf': 'documentos/a b.pdf',
            'https://s3.amazonaws.com/inversa-intranet/imagenes/user.png': 'imagenes/user.png',
            'https://s3.us-east-2.amazonaws.com/inversa-intranet/imagenes/user.png': 'imagenes/user.png',
        }
        for url, clave in casos.items():
            with self.subTest(url=url):
                self.assertEqual(clave_en_bucket(url, 'inversa-intranet'), clave)

    def test_otro_bucket_u_otro_servidor_no_es_de_este_bucket(self):
        for url in (
            'https://otro-bucket.s3.amazonaws.com/imagenes/user.png',
            'https://inversa-intranet.evil.com/imagenes/user.png',
            'https://evil.com/inversa-intranet/imagenes/user.png',
            'https://s3.amazonaws.com/otro/inversa-intranet/user.png',
            'https://inversa-intranet.s3.amazonaws.com/',
        ):
            with self.subTest(url=url):
                self.assertIsNone(clave_en_bucket(url, 'inversa-intranet'))


@override_settings(STORAGES=STORAGE_EN_MEMORIA)
class MigrarEnSitioTests(ApiTestCase):
    BUCKET = 'inversa-intranet'

    def setUp(self):
        super().setUp()
        self.categoria = _categoria()
        default_storage.save('documentos/balance.pdf', ContentFile(PDF, name='balance.pdf'))
        self.documento = Upload.objects.create(fname=f'https://{self.BUCKET}.s3.amazonaws.com/documentos/balance.pdf', name='Balance', area=self.categoria, estado=Upload.ACTIVO, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB')

    def _correr(self, *argumentos) -> str:
        salida = StringIO()
        with mock.patch('apps.core.management.commands.migrar_archivos_legados.urllib.request.urlopen') as abrir:
            call_command('migrar_archivos_legados', *argumentos, stdout=salida, stderr=salida)
        self.abrir = abrir
        return salida.getvalue()

    def test_el_archivo_que_ya_esta_en_el_bucket_no_se_descarga_y_la_fila_apunta_a_su_clave(self):
        self._correr('--aplicar', '--en-sitio', self.BUCKET)

        self.documento.refresh_from_db()
        self.assertEqual(self.documento.fname, 'storage:documentos/balance.pdf')
        self.abrir.assert_not_called()
        self.assertEqual(self.cliente_admin.get(reverse('documentos-documentos')).data['results'][0]['fname'], 'https://archivos.test/documentos/balance.pdf')

    def test_no_pasa_a_storage_un_archivo_que_no_esta_en_el_bucket(self):
        default_storage.delete('documentos/balance.pdf')

        texto = self._correr('--aplicar', '--en-sitio', self.BUCKET)

        self.documento.refresh_from_db()
        self.assertTrue(self.documento.fname.startswith('https://'))
        self.assertIn('no está en el bucket', texto)

    def test_el_ensayo_marca_lo_que_se_haria_en_sitio_y_no_cambia_nada(self):
        texto = self._correr('--en-sitio', self.BUCKET)

        self.assertIn('(en sitio)', texto)
        self.documento.refresh_from_db()
        self.assertTrue(self.documento.fname.startswith('https://'))
