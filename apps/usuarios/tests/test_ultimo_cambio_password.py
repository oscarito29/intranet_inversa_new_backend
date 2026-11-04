from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase
from apps.financial.models import Bitacora


def _cambio(correo: str, fecha) -> None:
    Bitacora.objects.create(usuario=correo, accion='Edicion', descripcion=f'Cambio de Password del Usuario {correo}', fecha=fecha)


class UltimoCambioDePasswordTests(ApiTestCase):
    def _ultimo(self):
        return self.cliente_usuario.get(reverse('perfil')).data['ultimo_cambio_password']

    def test_sin_cambios_previos_es_nulo(self):
        self.assertIsNone(self._ultimo())

    def test_tras_cambiar_la_contrasena_trae_la_fecha(self):
        cambio = self.cliente_usuario.post(
            reverse('cambiar-password'), {'actual': 'Clave-segura-123', 'nuevo': 'Otra-clave-456', 'repetido': 'Otra-clave-456'}, format='json'
        )
        self.assertEqual(cambio.status_code, 204)

        self.assertIsNotNone(self._ultimo())

    def test_toma_el_cambio_mas_reciente_y_solo_del_propio_usuario(self):
        ahora = timezone.now()
        _cambio(self.usuario.email, ahora - timedelta(days=30))
        _cambio(self.usuario.email, ahora - timedelta(days=2))
        _cambio(self.admin.email, ahora)

        ultimo = self._ultimo()

        self.assertLess(abs((ultimo - (ahora - timedelta(days=2))).total_seconds()), 5)

    def test_otras_ediciones_del_perfil_no_cuentan(self):
        Bitacora.objects.create(usuario=self.usuario.email, accion='Edicion', descripcion='Modifica su perfil', fecha=timezone.now())

        self.assertIsNone(self._ultimo())
