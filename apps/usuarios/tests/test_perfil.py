import shutil

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from apps.core.testing import ApiTestCase, crear_usuario
from apps.financial.models import Bitacora
from apps.usuarios.models import Usuario


class PerfilTests(ApiTestCase):
    def test_obtener_perfil(self):
        respuesta = self.cliente_usuario.get(reverse('perfil'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['email'], self.usuario.email)
        self.assertEqual(respuesta.data['rol_nombre'], 'User')
        self.assertFalse(respuesta.data['puede_editar_email'])

    def test_actualizar_nombre_y_celular(self):
        respuesta = self.cliente_usuario.patch(reverse('perfil'), {'name': 'Nuevo Nombre', 'phone_number': '88888888'}, format='json')

        self.assertEqual(respuesta.status_code, 200)
        self.usuario.refresh_from_db()
        self.assertEqual((self.usuario.name, self.usuario.phone_number), ('Nuevo Nombre', '88888888'))

    def test_validacion_de_nombre_corto(self):
        respuesta = self.cliente_usuario.patch(reverse('perfil'), {'name': 'ab', 'phone_number': '1'}, format='json')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('name', respuesta.data)

    def test_rol_usuario_no_puede_cambiar_su_correo(self):
        respuesta = self.cliente_usuario.patch(
            reverse('perfil'), {'name': 'Nombre Largo', 'phone_number': '1', 'email': 'otro@inversa.hn'}, format='json'
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['email'], ['Tu correo solo lo puede cambiar un administrador.'])

    def test_admin_puede_cambiar_su_correo_pero_no_repetir_uno_existente(self):
        ok = self.cliente_admin.patch(
            reverse('perfil'), {'name': 'Admin Nuevo', 'phone_number': '1', 'email': 'nuevo@inversa.hn'}, format='json'
        )
        repetido = self.cliente_admin.patch(
            reverse('perfil'), {'name': 'Admin Nuevo', 'phone_number': '1', 'email': self.usuario.email}, format='json'
        )

        self.assertEqual(ok.status_code, 200)
        self.assertEqual(repetido.status_code, 400)
        self.assertEqual(repetido.data['email'], ['Ya existe un usuario con ese correo.'])

    @override_settings(MEDIA_ROOT='media_test_perfil')
    def test_foto_valida_se_guarda_y_una_extension_invalida_se_rechaza(self):
        png = SimpleUploadedFile('foto.png', b'\x89PNG\r\n\x1a\n', content_type='image/png')
        ok = self.cliente_usuario.post(reverse('perfil-foto'), {'picture': png}, format='multipart')
        texto = SimpleUploadedFile('nota.txt', b'hola', content_type='text/plain')
        mal = self.cliente_usuario.post(reverse('perfil-foto'), {'picture': texto}, format='multipart')

        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.data['picture'].startswith('/media/perfiles/'))
        self.assertEqual(mal.status_code, 400)
        self.assertIn('picture', mal.data)
        shutil.rmtree('media_test_perfil', ignore_errors=True)


class CambiarPasswordTests(ApiTestCase):
    def _cambiar(self, actual='Clave-segura-123', nuevo='Nueva-clave-456', repetido='Nueva-clave-456'):
        return self.cliente_usuario.post(
            reverse('cambiar-password'), {'actual': actual, 'nuevo': nuevo, 'repetido': repetido}, format='json'
        )

    def test_cambio_correcto_actualiza_la_clave_y_registra_en_bitacora(self):
        respuesta = self._cambiar()

        self.assertEqual(respuesta.status_code, 204)
        self.assertTrue(Usuario.objects.get(pk=self.usuario.pk).check_password('Nueva-clave-456'))
        self.assertTrue(Bitacora.objects.filter(usuario=self.usuario.email, descripcion__startswith='Cambio de Password').exists())

    def test_clave_actual_incorrecta(self):
        respuesta = self._cambiar(actual='mala')

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['actual'], ['La contraseña actual es incorrecta.'])

    def test_claves_que_no_coinciden_o_demasiado_cortas(self):
        self.assertEqual(self._cambiar(repetido='distinta-12345').data['repetido'], ['Las contraseñas no coinciden.'])
        self.assertIn('nuevo', self._cambiar(nuevo='corta', repetido='corta').data)


class GestionDeUsuariosTests(ApiTestCase):
    def _payload(self, email='nuevo@inversa.hn'):
        return {
            'name': 'Nuevo',
            'email': email,
            'phone_number': '1',
            'address': 'x',
            'rol_id': 2,
            'estado': 'A',
            'userFinancieraId': '001',
            'password': 'Clave-segura-123',
        }

    def test_solo_un_admin_crea_o_edita_usuarios(self):
        self.assertEqual(self.cliente_usuario.post(reverse('usuarios-list-create'), self._payload(), format='json').status_code, 403)
        self.assertEqual(
            self.cliente_usuario.patch(reverse('usuarios-detail', args=[self.admin.pk]), {'name': 'x'}, format='json').status_code, 403
        )

    def test_admin_crea_y_edita(self):
        creado = self.cliente_admin.post(reverse('usuarios-list-create'), self._payload(), format='json')
        self.assertEqual(creado.status_code, 201)

        editado = self.cliente_admin.patch(reverse('usuarios-detail', args=[creado.data['id']]), {'name': 'Editado'}, format='json')
        self.assertEqual(editado.status_code, 200)
        self.assertEqual(editado.data['name'], 'Editado')

    def test_usuario_inexistente_es_404(self):
        self.assertEqual(self.cliente_admin.patch(reverse('usuarios-detail', args=[99999]), {'name': 'x'}, format='json').status_code, 404)

    def test_cualquiera_autenticado_lista_usuarios_y_catalogos(self):
        self.assertEqual(self.cliente_usuario.get(reverse('usuarios-list-create')).status_code, 200)
        for nombre in ('usuarios-roles', 'usuarios-financieras', 'usuarios-corporaciones'):
            self.assertEqual(self.cliente_usuario.get(reverse(nombre)).status_code, 200)
