from datetime import date
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase, cliente_de, crear_usuario
from apps.financial.models import Documento, RangoFecha
from apps.financial.selectors import MAX_FALTANTES, _mes_que_se_cierra
from apps.usuarios.models import Financiera

# El 4 de noviembre se cierra octubre, el mes que los catálogos de prueba traen.
HOY = date(2026, 11, 4)


def _documento(estado=Documento.PENDIENTE, financiera_id='001', corporacion_id='001') -> Documento:
    return Documento.objects.create(
        nombre_archivo='estado.pdf',
        ruta_archivo='/media/documentos/estado.pdf',
        doc_aprobado=estado,
        anio_id=2026,
        mes_id=10,
        corporacion_id=corporacion_id,
        financiera_id=financiera_id,
        fecha=timezone.now(),
        email_usuario_sube='sube@inversa.hn',
    )


def _ventana(desde: date, hasta: date) -> None:
    RangoFecha.objects.create(desde=desde, hasta=hasta, email_usuario='admin@inversa.hn')


class MesQueSeCierraTests(ApiTestCase):
    def test_es_el_mes_anterior_al_de_hoy(self):
        self.assertEqual(_mes_que_se_cierra(date(2026, 11, 4)), (2026, 10))
        self.assertEqual(_mes_que_se_cierra(date(2026, 11, 30)), (2026, 10))

    def test_en_enero_se_cierra_diciembre_del_año_anterior(self):
        self.assertEqual(_mes_que_se_cierra(date(2027, 1, 5)), (2026, 12))


class PanoramaTests(ApiTestCase):
    def _pedir(self, cliente=None):
        with patch('apps.financial.selectors.timezone.localdate', return_value=HOY):
            return (cliente or self.cliente_admin).get(reverse('financiero-panorama'))

    def test_exige_autenticacion(self):
        self.assertEqual(self._pedir(cliente_de(None)).status_code, 401)

    def test_dice_que_periodo_se_cierra(self):
        periodo = self._pedir().data['periodo']

        self.assertEqual(periodo, {'anio_id': 2026, 'anio_numero': 2026, 'mes_id': 10, 'mes_nombre': 'Octubre'})

    def test_el_administrador_ve_cada_corporacion_con_lo_que_cargo_y_lo_que_falta(self):
        _documento(estado=Documento.APROBADO, financiera_id='001')

        corporaciones = {c['id']: c for c in self._pedir().data['corporaciones']}

        self.assertEqual(set(corporaciones), {'001', '002'})
        self.assertEqual(
            (corporaciones['001']['nombre'], corporaciones['001']['total'], corporaciones['001']['cargadas'], corporaciones['001']['faltan']),
            ('FINANCIERAS', 2, 1, 1),
        )
        self.assertEqual(corporaciones['001']['por_estado']['aprobado'], 1)
        self.assertEqual((corporaciones['002']['total'], corporaciones['002']['cargadas'], corporaciones['002']['faltan']), (1, 0, 1))

    def test_quien_sube_ve_solo_su_entidad(self):
        corporaciones = self._pedir(self.cliente_usuario).data['corporaciones']

        self.assertEqual([(c['id'], c['total']) for c in corporaciones], [('001', 1)])

    def test_quien_sube_recibe_la_lista_de_lo_que_aun_no_cargo(self):
        faltan = self._pedir(self.cliente_usuario).data['faltan']

        self.assertEqual(faltan['total'], 1)
        self.assertEqual(faltan['items'], [{'financiera_id': '001', 'financiera_nombre': 'FINANCIERA A', 'corporacion_id': '001'}])

    def test_lo_ya_cargado_deja_de_faltar_aunque_este_pendiente(self):
        _documento(estado=Documento.PENDIENTE, financiera_id='001')

        self.assertEqual(self._pedir(self.cliente_usuario).data['faltan']['total'], 0)

    def test_un_documento_rechazado_no_cuenta_como_falta_porque_ya_sale_en_para_corregir(self):
        _documento(estado=Documento.RECHAZADO, financiera_id='001')

        self.assertEqual(self._pedir(self.cliente_usuario).data['faltan']['total'], 0)

    def test_quien_solo_consulta_ve_todo_y_no_recibe_faltantes_porque_no_sube(self):
        consulta = cliente_de(crear_usuario(rol_id=4, financiera_id='001'))

        datos = self._pedir(consulta).data

        self.assertEqual({c['id'] for c in datos['corporaciones']}, {'001', '002'})
        self.assertEqual(datos['faltan'], {'total': 0, 'items': []})

    def test_los_faltantes_se_cuentan_todos_pero_se_listan_pocos(self):
        for numero in range(10, 10 + MAX_FALTANTES + 3):
            Financiera.objects.create(id=f'0{numero}', nombre=f'EXTRA {numero}', corporacion_id='001')

        faltan = self._pedir().data['faltan']

        self.assertEqual(faltan['total'], 3 + MAX_FALTANTES + 3)
        self.assertEqual(len(faltan['items']), MAX_FALTANTES)

    def test_sin_ventana_configurada_no_hay_ventana(self):
        self.assertIsNone(self._pedir().data['ventana'])

    def test_ventana_abierta_dice_cuantos_dias_quedan(self):
        _ventana(date(2026, 11, 1), date(2026, 11, 10))

        self.assertEqual(self._pedir().data['ventana'], {'desde': '2026-11-01', 'hasta': '2026-11-10', 'estado': 'abierta', 'dias': 6})

    def test_el_ultimo_dia_de_la_ventana_quedan_cero_dias_y_sigue_abierta(self):
        _ventana(date(2026, 11, 1), date(2026, 11, 4))

        ventana = self._pedir().data['ventana']

        self.assertEqual((ventana['estado'], ventana['dias']), ('abierta', 0))

    def test_ventana_cerrada_no_tiene_dias(self):
        _ventana(date(2026, 10, 1), date(2026, 10, 10))

        ventana = self._pedir().data['ventana']

        self.assertEqual((ventana['estado'], ventana['dias']), ('cerrada', None))

    def test_ventana_proxima_dice_cuantos_dias_faltan_para_que_abra(self):
        _ventana(date(2026, 11, 9), date(2026, 11, 20))

        ventana = self._pedir().data['ventana']

        self.assertEqual((ventana['estado'], ventana['dias']), ('proxima', 5))
