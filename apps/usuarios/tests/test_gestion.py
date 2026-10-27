from django.urls import reverse

from apps.core.testing import ApiTestCase, crear_usuario
from apps.financial.models import Bitacora
from apps.usuarios.models import Usuario


def _payload(email='nuevo@inversa.hn', **extra):
    return {
        'name': 'Nuevo',
        'email': email,
        'phone_number': '99999999',
        'address': 'Calle 1',
        'rol_id': 2,
        'estado': 'A',
        'userFinancieraId': '001',
        'password': 'Clave-segura-123',
        **extra,
    }


class DetalleDeUsuarioTests(ApiTestCase):
    def test_el_admin_ve_un_usuario(self):
        respuesta = self.cliente_admin.get(reverse('usuarios-detail', args=[self.usuario.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['email'], self.usuario.email)

    def test_un_usuario_normal_no_ve_a_otros(self):
        self.assertEqual(self.cliente_usuario.get(reverse('usuarios-detail', args=[self.admin.pk])).status_code, 403)

    def test_usuario_inexistente_es_404(self):
        self.assertEqual(self.cliente_admin.get(reverse('usuarios-detail', args=[99999])).status_code, 404)


class BitacoraDeUsuariosTests(ApiTestCase):
    def test_crear_y_editar_quedan_en_la_bitacora(self):
        creado = self.cliente_admin.post(reverse('usuarios-list-create'), _payload(), format='json')
        self.cliente_admin.patch(reverse('usuarios-detail', args=[creado.data['id']]), {'name': 'Editado'}, format='json')

        descripciones = set(Bitacora.objects.filter(usuario=self.admin.email).values_list('descripcion', flat=True))

        self.assertIn('Crea el usuario nuevo@inversa.hn', descripciones)
        self.assertIn('Modifica el usuario nuevo@inversa.hn', descripciones)

    def test_un_correo_repetido_es_400(self):
        respuesta = self.cliente_admin.post(reverse('usuarios-list-create'), _payload(email=self.usuario.email), format='json')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('email', respuesta.data)


class AutoproteccionDelAdminTests(ApiTestCase):
    def _editar_a_si_mismo(self, **cambios):
        return self.cliente_admin.patch(reverse('usuarios-detail', args=[self.admin.pk]), cambios, format='json')

    def test_no_puede_desactivar_su_propia_cuenta(self):
        respuesta = self._editar_a_si_mismo(estado='I')

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['estado'], ['No puedes desactivar tu propia cuenta.'])
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.estado, 'A')

    def test_no_puede_quitarse_el_rol_de_administrador(self):
        respuesta = self._editar_a_si_mismo(rol_id=2)

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('rol_id', respuesta.data)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.rol_id, 1)

    def test_si_puede_cambiar_otros_datos_propios(self):
        self.assertEqual(self._editar_a_si_mismo(name='Admin Nuevo').status_code, 200)

    def test_si_puede_desactivar_o_degradar_a_otro_administrador(self):
        crear_usuario(rol_id=1, email='tercero.admin@inversa.hn')  # con tres, quitar uno deja los dos que se exigen
        otro = crear_usuario(rol_id=1, email='otro.admin@inversa.hn')

        respuesta = self.cliente_admin.patch(reverse('usuarios-detail', args=[otro.pk]), {'estado': 'I', 'rol_id': 2}, format='json')

        self.assertEqual(respuesta.status_code, 200)


class RestablecerPasswordTests(ApiTestCase):
    def _restablecer(self, usuario, cliente=None):
        return (cliente or self.cliente_admin).post(reverse('usuarios-restablecer-password', args=[usuario.pk]))

    def test_devuelve_una_contrasena_temporal_con_la_que_el_usuario_puede_entrar(self):
        respuesta = self._restablecer(self.usuario)

        self.assertEqual(respuesta.status_code, 200)
        temporal = respuesta.data['password_temporal']
        self.assertGreaterEqual(len(temporal), 12)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(temporal))
        self.assertFalse(self.usuario.check_password('Clave-segura-123'))

    def test_cada_restablecimiento_da_una_clave_distinta(self):
        primera = self._restablecer(self.usuario).data['password_temporal']
        segunda = self._restablecer(self.usuario).data['password_temporal']

        self.assertNotEqual(primera, segunda)

    def test_la_clave_no_se_guarda_en_texto_plano_ni_en_la_bitacora(self):
        temporal = self._restablecer(self.usuario).data['password_temporal']

        self.usuario.refresh_from_db()
        self.assertNotEqual(self.usuario.password, temporal)
        self.assertFalse(any(temporal in texto for texto in Bitacora.objects.values_list('descripcion', flat=True)))

    def test_queda_en_la_bitacora_como_cambio_de_contrasena_del_usuario(self):
        self._restablecer(self.usuario)

        registro = Bitacora.objects.get(descripcion=f'Cambio de Password del Usuario {self.usuario.email}')

        self.assertEqual(registro.usuario, self.admin.email)

    def test_el_perfil_del_usuario_muestra_la_fecha_del_restablecimiento(self):
        self.assertIsNone(self.cliente_usuario.get(reverse('perfil')).data['ultimo_cambio_password'])

        self._restablecer(self.usuario)

        self.assertIsNotNone(self.cliente_usuario.get(reverse('perfil')).data['ultimo_cambio_password'])

    def test_solo_un_admin_restablece(self):
        respuesta = self._restablecer(self.admin, cliente=self.cliente_usuario)

        self.assertEqual(respuesta.status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('Clave-segura-123'))

    def test_un_admin_no_restablece_su_propia_contrasena_aqui(self):
        respuesta = self._restablecer(self.admin)

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('Mi perfil', respuesta.data['detail'])

    def test_usuario_inexistente_es_404(self):
        respuesta = self.cliente_admin.post(reverse('usuarios-restablecer-password', args=[99999]))

        self.assertEqual(respuesta.status_code, 404)

    def test_no_hay_ningun_cambio_si_el_usuario_no_existe(self):
        antes = Bitacora.objects.count()
        self.cliente_admin.post(reverse('usuarios-restablecer-password', args=[99999]))

        self.assertEqual(Bitacora.objects.count(), antes)
        self.assertEqual(Usuario.objects.filter(email=self.usuario.email).count(), 1)
