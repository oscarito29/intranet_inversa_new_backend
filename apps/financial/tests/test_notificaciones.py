from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase, crear_usuario, cliente_de
from apps.financial.models import Documento
from apps.financial.selectors import MAX_NOTIFICACIONES


def _documento(estado=Documento.PENDIENTE, financiera_id='001', **extra) -> Documento:
    return Documento.objects.create(
        nombre_archivo=extra.pop('nombre_archivo', 'estado.pdf'),
        ruta_archivo='/media/documentos/estado.pdf',
        doc_aprobado=estado,
        anio_id=2026,
        mes_id=10,
        corporacion_id='001',
        financiera_id=financiera_id,
        fecha=extra.pop('fecha', timezone.now()),
        email_usuario_sube='sube@inversa.hn',
        **extra,
    )


class NotificacionesTests(ApiTestCase):
    def _pedir(self, cliente):
        return cliente.get(reverse('financiero-notificaciones'))

    def test_exige_autenticacion(self):
        self.assertEqual(self._pedir(cliente_de(None)).status_code, 401)

    def test_el_administrador_ve_los_pendientes_de_todas_las_financieras(self):
        _documento(financiera_id='001')
        _documento(financiera_id='002')
        _documento(estado=Documento.APROBADO)

        datos = self._pedir(self.cliente_admin).data

        self.assertEqual(datos['total'], 2)
        self.assertEqual({item['financiera_id'] for item in datos['items']}, {'001', '002'})
        self.assertTrue(all(item['tipo'] == 'pendiente' for item in datos['items']))

    def test_los_documentos_con_estado_nulo_cuentan_como_pendientes(self):
        _documento(estado=None)

        self.assertEqual(self._pedir(self.cliente_admin).data['total'], 1)

    def test_el_administrador_no_recibe_avisos_de_rechazos(self):
        _documento(estado=Documento.RECHAZADO, fecha_rechaza=timezone.now(), motivo_rechazo='Ilegible')

        self.assertEqual(self._pedir(self.cliente_admin).data['total'], 0)

    def test_cada_aviso_trae_lo_necesario_para_abrir_el_documento(self):
        _documento(nombre_archivo='septiembre.pdf', financiera_id='002')

        item = self._pedir(self.cliente_admin).data['items'][0]

        self.assertEqual(
            (item['nombre_archivo'], item['financiera_nombre'], item['anio_numero'], item['mes_nombre'], item['corporacion_id']),
            ('septiembre.pdf', 'FINANCIERA B', 2026, 'Octubre', '001'),
        )
        self.assertIsNotNone(item['documento_id'])

    def test_el_usuario_ve_solo_los_rechazos_y_revocaciones_de_su_financiera(self):
        _documento(estado=Documento.RECHAZADO, fecha_rechaza=timezone.now(), motivo_rechazo='Ilegible')
        _documento(estado=Documento.REVOCADO, fecha_desaprueba=timezone.now(), motivo_desaprueba='Cifras erradas')
        _documento(estado=Documento.RECHAZADO, financiera_id='002', fecha_rechaza=timezone.now(), motivo_rechazo='Ajeno')
        _documento(estado=Documento.PENDIENTE)
        _documento(estado=Documento.APROBADO)

        datos = self._pedir(self.cliente_usuario).data

        self.assertEqual(datos['total'], 2)
        self.assertEqual({(i['tipo'], i['motivo']) for i in datos['items']}, {('rechazado', 'Ilegible'), ('revocado', 'Cifras erradas')})

    def test_el_usuario_no_ve_avisos_con_mas_de_treinta_dias(self):
        _documento(estado=Documento.RECHAZADO, fecha_rechaza=timezone.now() - timedelta(days=31), motivo_rechazo='Viejo')
        _documento(estado=Documento.RECHAZADO, fecha_rechaza=timezone.now() - timedelta(days=29), motivo_rechazo='Reciente')

        datos = self._pedir(self.cliente_usuario).data

        self.assertEqual([i['motivo'] for i in datos['items']], ['Reciente'])

    def test_los_avisos_del_usuario_salen_del_mas_reciente_al_mas_antiguo(self):
        ahora = timezone.now()
        _documento(estado=Documento.RECHAZADO, fecha_rechaza=ahora - timedelta(days=3), motivo_rechazo='Antiguo')
        _documento(estado=Documento.REVOCADO, fecha_desaprueba=ahora - timedelta(hours=1), motivo_desaprueba='Nuevo')

        datos = self._pedir(self.cliente_usuario).data

        self.assertEqual([i['motivo'] for i in datos['items']], ['Nuevo', 'Antiguo'])

    def test_trae_como_maximo_veinte_avisos_pero_cuenta_todos(self):
        for numero in range(MAX_NOTIFICACIONES + 5):
            _documento(nombre_archivo=f'estado-{numero}.pdf')

        datos = self._pedir(self.cliente_admin).data

        self.assertEqual(datos['total'], MAX_NOTIFICACIONES + 5)
        self.assertEqual(len(datos['items']), MAX_NOTIFICACIONES)

    def test_las_consultas_no_crecen_con_la_cantidad_de_avisos(self):
        _documento()
        with self.assertNumQueries(2):
            self._pedir(self.cliente_admin)
        for numero in range(8):
            _documento(financiera_id='002' if numero % 2 else '001')
        with self.assertNumQueries(2):
            self._pedir(self.cliente_admin)
