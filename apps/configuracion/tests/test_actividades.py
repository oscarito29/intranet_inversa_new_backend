from datetime import date, time

from django.urls import reverse

from apps.configuracion.models import Actividad
from apps.core.testing import ApiTestCase
from apps.financial.models import Bitacora


def _actividad(**extra) -> Actividad:
    datos = {'fecha': date(2026, 11, 5), 'titulo': 'Capacitación', 'descripcion': 'Sala 2', 'hora_desde': time(9, 0), 'hora_hasta': time(10, 0)}
    return Actividad.objects.create(**{**datos, **extra})


class CrearActividadTests(ApiTestCase):
    def _crear(self, **datos):
        return self.cliente_admin.post(reverse('configuracion-actividades'), {'fecha': '2026-11-05', 'titulo': 'Reunión', **datos}, format='json')

    def test_crea_con_horas_y_queda_en_la_bitacora(self):
        respuesta = self._crear(descripcion='Sala 1', hora_desde='09:00', hora_hasta='10:30')

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data['hora_hasta'], '10:30:00')
        self.assertTrue(Bitacora.objects.filter(usuario=self.admin.email, descripcion='Crea la actividad Reunión').exists())

    def test_las_horas_son_opcionales_y_una_cadena_vacia_cuenta_como_sin_hora(self):
        respuesta = self._crear(hora_desde='', hora_hasta='')

        self.assertEqual(respuesta.status_code, 201)
        self.assertIsNone(respuesta.data['hora_desde'])

    def test_la_hora_final_no_puede_ser_anterior_a_la_inicial(self):
        respuesta = self._crear(hora_desde='10:00', hora_hasta='09:00')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('hora_hasta', respuesta.data)
        self.assertEqual(Actividad.objects.count(), 0)

    def test_una_hora_con_formato_invalido_es_400(self):
        self.assertEqual(self._crear(hora_desde='mañana').status_code, 400)

    def test_una_fecha_invalida_es_400(self):
        self.assertEqual(self._crear(fecha='no-es-fecha').status_code, 400)


class EditarActividadTests(ApiTestCase):
    def _editar(self, actividad, datos, cliente=None):
        return (cliente or self.cliente_admin).patch(reverse('configuracion-actividad-detail', args=[actividad.pk]), datos, format='json')

    def test_cambia_solo_lo_enviado(self):
        actividad = _actividad()

        respuesta = self._editar(actividad, {'titulo': 'Capacitación nueva'})

        self.assertEqual(respuesta.status_code, 200)
        actividad.refresh_from_db()
        self.assertEqual(actividad.titulo, 'Capacitación nueva')
        self.assertEqual((actividad.descripcion, actividad.hora_desde, actividad.fecha), ('Sala 2', time(9, 0), date(2026, 11, 5)))

    def test_se_puede_quitar_la_hora_enviando_nulo(self):
        actividad = _actividad()

        self._editar(actividad, {'hora_desde': None, 'hora_hasta': None})

        actividad.refresh_from_db()
        self.assertIsNone(actividad.hora_desde)

    def test_valida_las_horas_contra_los_valores_ya_guardados(self):
        actividad = _actividad(hora_desde=time(9, 0), hora_hasta=time(10, 0))

        respuesta = self._editar(actividad, {'hora_desde': '11:00'})

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('hora_hasta', respuesta.data)
        actividad.refresh_from_db()
        self.assertEqual(actividad.hora_desde, time(9, 0))

    def test_solo_un_admin_edita(self):
        actividad = _actividad()

        self.assertEqual(self._editar(actividad, {'titulo': 'x'}, cliente=self.cliente_usuario).status_code, 403)
        actividad.refresh_from_db()
        self.assertEqual(actividad.titulo, 'Capacitación')

    def test_actividad_inexistente_es_404(self):
        self.assertEqual(self.cliente_admin.patch(reverse('configuracion-actividad-detail', args=[999]), {'titulo': 'x'}, format='json').status_code, 404)

    def test_el_cambio_queda_en_la_bitacora(self):
        actividad = _actividad()

        self._editar(actividad, {'titulo': 'Nueva'})

        self.assertTrue(Bitacora.objects.filter(descripcion='Modifica la actividad Nueva', usuario=self.admin.email).exists())

    def test_la_lista_cacheada_se_actualiza_al_editar(self):
        actividad = _actividad()
        self.assertEqual(self.cliente_usuario.get(reverse('configuracion-actividades')).data[0]['titulo'], 'Capacitación')

        with self.captureOnCommitCallbacks(execute=True):
            self._editar(actividad, {'titulo': 'Cambiada'})

        self.assertEqual(self.cliente_usuario.get(reverse('configuracion-actividades')).data[0]['titulo'], 'Cambiada')


class EliminarActividadTests(ApiTestCase):
    def test_elimina_y_queda_en_la_bitacora(self):
        actividad = _actividad()

        respuesta = self.cliente_admin.delete(reverse('configuracion-actividad-detail', args=[actividad.pk]))

        self.assertEqual(respuesta.status_code, 204)
        self.assertFalse(Actividad.objects.filter(pk=actividad.pk).exists())
        self.assertTrue(Bitacora.objects.filter(descripcion='Elimina la actividad Capacitación').exists())

    def test_solo_un_admin_elimina(self):
        actividad = _actividad()

        self.assertEqual(self.cliente_usuario.delete(reverse('configuracion-actividad-detail', args=[actividad.pk])).status_code, 403)
        self.assertTrue(Actividad.objects.filter(pk=actividad.pk).exists())

    def test_actividad_inexistente_es_404(self):
        self.assertEqual(self.cliente_admin.delete(reverse('configuracion-actividad-detail', args=[999])).status_code, 404)

    def test_la_lista_cacheada_se_actualiza_al_eliminar(self):
        actividad = _actividad()
        self.assertEqual(len(self.cliente_usuario.get(reverse('configuracion-actividades')).data), 1)

        with self.captureOnCommitCallbacks(execute=True):
            self.cliente_admin.delete(reverse('configuracion-actividad-detail', args=[actividad.pk]))

        self.assertEqual(self.cliente_usuario.get(reverse('configuracion-actividades')).data, [])
