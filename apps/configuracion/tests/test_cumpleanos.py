from datetime import date

from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase, cliente_de, crear_usuario


def _cumple_este_mes(dia: int, anio: int = 1990) -> date:
    hoy = timezone.localdate()
    return date(anio, hoy.month, dia)


class CumpleanosPrivacidadTests(ApiTestCase):
    def _pedir(self, cliente=None):
        return (cliente or self.cliente_usuario).get(reverse('configuracion-cumpleanos'))

    def test_exige_autenticacion(self):
        self.assertEqual(self._pedir(cliente_de(None)).status_code, 401)

    def test_solo_salen_el_dia_y_el_mes_nunca_el_anio_de_nacimiento(self):
        crear_usuario(name='Ana', fecha_nacimiento=_cumple_este_mes(14, anio=1987))

        fila = self._pedir().data[0]

        self.assertEqual(set(fila), {'id', 'name', 'cumple_dia', 'cumple_mes'})
        self.assertEqual((fila['cumple_dia'], fila['cumple_mes']), (14, timezone.localdate().month))
        self.assertNotIn('1987', str(self._pedir().data))

    def test_no_salen_las_personas_inactivas_ni_las_dadas_de_baja(self):
        crear_usuario(name='Inactiva', estado='I', fecha_nacimiento=_cumple_este_mes(10))
        crear_usuario(name='De baja', deleted_at=timezone.now(), fecha_nacimiento=_cumple_este_mes(11))
        crear_usuario(name='Activa', fecha_nacimiento=_cumple_este_mes(12))

        self.assertEqual([c['name'] for c in self._pedir().data], ['Activa'])

    def test_no_salen_las_de_otros_meses_ni_las_que_no_tienen_fecha(self):
        hoy = timezone.localdate()
        otro_mes = 1 if hoy.month != 1 else 2
        crear_usuario(name='Otro mes', fecha_nacimiento=date(1990, otro_mes, 5))
        crear_usuario(name='Sin fecha', fecha_nacimiento=None)

        self.assertEqual(self._pedir().data, [])

    def test_van_ordenadas_por_dia_del_mes_y_no_por_anio(self):
        crear_usuario(name='Tarde y joven', fecha_nacimiento=_cumple_este_mes(25, anio=2001))
        crear_usuario(name='Temprano y mayor', fecha_nacimiento=_cumple_este_mes(3, anio=1960))
        crear_usuario(name='En medio', fecha_nacimiento=_cumple_este_mes(15, anio=1985))

        self.assertEqual([c['name'] for c in self._pedir().data], ['Temprano y mayor', 'En medio', 'Tarde y joven'])
