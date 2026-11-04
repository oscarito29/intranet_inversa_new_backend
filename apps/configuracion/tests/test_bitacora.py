from datetime import datetime, timedelta

from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase, cliente_de
from apps.financial.models import Bitacora


def _registro(usuario='maria@inversa.hn', accion='Edicion', descripcion='Modifica el usuario x', fecha=None) -> Bitacora:
    return Bitacora.objects.create(usuario=usuario, accion=accion, descripcion=descripcion, fecha=fecha or timezone.now())


def _dia(anio, mes, dia, hora=12):
    return timezone.make_aware(datetime(anio, mes, dia, hora, 0))


class BitacoraTests(ApiTestCase):
    def _pedir(self, cliente=None, **parametros):
        return (cliente or self.cliente_admin).get(reverse('configuracion-bitacora'), parametros)

    def test_exige_autenticacion(self):
        self.assertEqual(self._pedir(cliente_de(None)).status_code, 401)

    def test_un_usuario_normal_no_puede_leerla(self):
        self.assertEqual(self._pedir(self.cliente_usuario).status_code, 403)

    def test_lista_de_lo_mas_reciente_a_lo_mas_antiguo(self):
        _registro(descripcion='antigua', fecha=_dia(2026, 10, 1))
        _registro(descripcion='reciente', fecha=_dia(2026, 10, 20))

        respuesta = self._pedir()

        self.assertEqual([fila['descripcion'] for fila in respuesta.data['results']], ['reciente', 'antigua'])
        self.assertEqual(set(respuesta.data['results'][0]), {'id', 'usuario', 'accion', 'descripcion', 'fecha'})

    def test_busca_por_persona_o_por_descripcion_sin_distinguir_mayusculas(self):
        _registro(usuario='maria@inversa.hn', descripcion='Sube el documento A')
        _registro(usuario='pedro@inversa.hn', descripcion='Aprueba documento 7')
        _registro(usuario='pedro@inversa.hn', descripcion='Crea la actividad Taller')

        por_persona = self._pedir(q='MARIA').data
        por_descripcion = self._pedir(q='documento').data

        self.assertEqual(por_persona['count'], 1)
        self.assertEqual(por_descripcion['count'], 2)

    def test_filtra_por_accion(self):
        _registro(accion='Aprobacion')
        _registro(accion='Rechazo')

        respuesta = self._pedir(accion='Rechazo').data

        self.assertEqual([fila['accion'] for fila in respuesta['results']], ['Rechazo'])

    def test_los_dias_desde_y_hasta_se_incluyen_completos(self):
        _registro(descripcion='antes', fecha=_dia(2026, 10, 9, hora=23))
        _registro(descripcion='primer dia', fecha=_dia(2026, 10, 10, hora=0))
        _registro(descripcion='ultimo dia', fecha=_dia(2026, 10, 12, hora=23))
        _registro(descripcion='despues', fecha=_dia(2026, 10, 13, hora=0))

        respuesta = self._pedir(desde='2026-10-10', hasta='2026-10-12').data

        self.assertEqual({fila['descripcion'] for fila in respuesta['results']}, {'primer dia', 'ultimo dia'})

    def test_la_fecha_final_no_puede_ser_anterior_a_la_inicial(self):
        respuesta = self._pedir(desde='2026-10-12', hasta='2026-10-10')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('hasta', respuesta.data)

    def test_pagina_y_dice_cuantas_paginas_hay(self):
        for numero in range(7):
            _registro(descripcion=f'registro {numero}', fecha=timezone.now() - timedelta(minutes=numero))

        primera = self._pedir(page_size=3).data
        ultima = self._pedir(page_size=3, page=3).data

        self.assertEqual((primera['count'], primera['total_pages'], len(primera['results'])), (7, 3, 3))
        self.assertEqual((ultima['page'], len(ultima['results'])), (3, 1))
        self.assertEqual(primera['results'][0]['descripcion'], 'registro 0')

    def test_las_paginas_no_repiten_registros_con_la_misma_fecha(self):
        misma_fecha = timezone.now()
        for numero in range(5):
            _registro(descripcion=f'igual {numero}', fecha=misma_fecha)

        vistos = [fila['id'] for pagina in (1, 2, 3) for fila in self._pedir(page_size=2, page=pagina).data['results']]

        self.assertEqual(len(vistos), len(set(vistos)))
        self.assertEqual(len(vistos), 5)

    def test_lista_las_acciones_que_existen_para_el_filtro(self):
        _registro(accion='Rechazo')
        _registro(accion='Aprobacion')
        _registro(accion='Rechazo')

        self.assertEqual(self._pedir().data['acciones'], ['Aprobacion', 'Rechazo'])

    def test_una_accion_del_administrador_aparece_en_su_propia_bitacora(self):
        self.cliente_admin.post(reverse('configuracion-actividades'), {'fecha': '2026-11-05', 'titulo': 'Reunión'}, format='json')

        respuesta = self._pedir(q='Reunión').data

        self.assertEqual(respuesta['count'], 1)
        self.assertEqual(respuesta['results'][0]['usuario'], self.admin.email)

    def test_las_consultas_no_crecen_con_las_filas(self):
        _registro()
        self._pedir()  # calienta la caché de acciones para contar solo las consultas de la página
        with self.assertNumQueries(2):
            self._pedir()
        for numero in range(10):
            _registro(descripcion=f'fila {numero}')
        with self.assertNumQueries(2):
            self._pedir()
