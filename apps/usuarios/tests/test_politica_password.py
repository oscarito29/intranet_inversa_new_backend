from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.testing import ApiTestCase, crear_usuario
from apps.usuarios.models import Usuario
from apps.usuarios.services import validar_politica_de_password

ACTUAL = 'Clave-segura-123'
NUEVA_BUENA = 'Otra-clave-segura-456'


class CambiarPasswordTests(ApiTestCase):
    def _cambiar(self, nuevo: str, actual: str = ACTUAL):
        return self.cliente_usuario.post(reverse('cambiar-password'), {'actual': actual, 'nuevo': nuevo, 'repetido': nuevo}, format='json')

    def test_una_contrasena_valida_se_cambia(self):
        self.assertEqual(self._cambiar(NUEVA_BUENA).status_code, 204)
        self.assertTrue(Usuario.objects.get(pk=self.usuario.pk).check_password(NUEVA_BUENA))

    def test_exige_al_menos_diez_caracteres(self):
        respuesta = self._cambiar('Corta-123')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('nuevo', respuesta.data)
        self.assertIn('10 caracteres', ' '.join(respuesta.data['nuevo']))

    def test_diez_caracteres_justos_alcanzan(self):
        self.assertEqual(self._cambiar('Corta-1234').status_code, 204)

    def test_no_acepta_una_contrasena_solo_de_numeros(self):
        respuesta = self._cambiar('1928374650192')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('nuevo', respuesta.data)

    def test_no_acepta_una_contrasena_comun(self):
        self.assertEqual(self._cambiar('password123').status_code, 400)

    def test_no_acepta_una_parecida_al_correo(self):
        self.assertEqual(self._cambiar(self.usuario.email).status_code, 400)

    def test_no_acepta_una_parecida_al_nombre(self):
        persona = crear_usuario(name='Marcela', email='otra@inversa.hn')

        with self.assertRaises(ValidationError):
            validar_politica_de_password('marcela2026', persona, 'nuevo')

    def test_no_se_puede_repetir_la_actual(self):
        respuesta = self._cambiar(ACTUAL)

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('igual a la actual', ' '.join(respuesta.data['nuevo']))

    def test_una_clave_rechazada_no_cambia_nada(self):
        self._cambiar('1928374650192')

        self.assertTrue(Usuario.objects.get(pk=self.usuario.pk).check_password(ACTUAL))

    def test_los_motivos_salen_en_espanol(self):
        mensajes = ' '.join(self._cambiar('abc').data['nuevo'])

        self.assertIn('caracteres', mensajes)

    def test_la_actual_incorrecta_se_sigue_diciendo(self):
        respuesta = self._cambiar(NUEVA_BUENA, actual='mala')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('actual', respuesta.data)


class ContrasenaQueEscribeElAdministradorTests(ApiTestCase):
    def _datos(self, password: str, **extra):
        return {
            'name': 'Nuevo',
            'email': 'nuevo@inversa.hn',
            'phone_number': '99999999',
            'address': 'Calle 1',
            'rol_id': 2,
            'estado': 'A',
            'userFinancieraId': '001',
            'password': password,
            **extra,
        }

    def test_al_crear_una_contrasena_debil_se_rechaza_y_no_se_crea_la_persona(self):
        respuesta = self.cliente_admin.post(reverse('usuarios-list-create'), self._datos('1234567'), format='json')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('password', respuesta.data)
        self.assertFalse(Usuario.objects.filter(email='nuevo@inversa.hn').exists())

    def test_al_crear_una_contrasena_parecida_al_correo_se_rechaza(self):
        respuesta = self.cliente_admin.post(reverse('usuarios-list-create'), self._datos('nuevo@inversa.hn'), format='json')

        self.assertEqual(respuesta.status_code, 400)

    def test_al_crear_una_contrasena_buena_se_acepta(self):
        respuesta = self.cliente_admin.post(reverse('usuarios-list-create'), self._datos(NUEVA_BUENA), format='json')

        self.assertEqual(respuesta.status_code, 201)

    def test_al_editar_sin_contrasena_no_se_valida_nada(self):
        persona = crear_usuario(email='otra@inversa.hn')

        respuesta = self.cliente_admin.patch(reverse('usuarios-detail', args=[persona.pk]), {'name': 'Editada'}, format='json')

        self.assertEqual(respuesta.status_code, 200)

    def test_al_editar_una_contrasena_debil_se_rechaza_y_la_anterior_sigue_valiendo(self):
        persona = crear_usuario(email='otra@inversa.hn')

        respuesta = self.cliente_admin.patch(reverse('usuarios-detail', args=[persona.pk]), {'password': 'corta'}, format='json')

        self.assertEqual(respuesta.status_code, 400)
        self.assertTrue(Usuario.objects.get(pk=persona.pk).check_password(ACTUAL))

    def test_la_temporal_que_genera_el_sistema_no_pasa_por_la_politica(self):
        persona = crear_usuario(email='otra@inversa.hn')

        respuesta = self.cliente_admin.post(reverse('usuarios-restablecer-password', args=[persona.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertGreaterEqual(len(respuesta.data['password_temporal']), 10)
