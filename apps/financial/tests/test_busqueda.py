from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase, cliente_de, crear_usuario
from apps.financial.models import Documento
from apps.financial.selectors import MAX_RESULTADOS_DE_BUSQUEDA


def _documento(nombre='estado.pdf', financiera_id='001', estado=Documento.APROBADO, corporacion_id='001', **extra) -> Documento:
    return Documento.objects.create(
        nombre_archivo=nombre,
        ruta_archivo='/media/documentos/estado.pdf',
        doc_aprobado=estado,
        anio_id=2026,
        mes_id=10,
        corporacion_id=corporacion_id,
        financiera_id=financiera_id,
        fecha=extra.pop('fecha', timezone.now()),
        email_usuario_sube='sube@inversa.hn',
        **extra,
    )


class BuscarDocumentosTests(ApiTestCase):
    def _buscar(self, texto, cliente=None):
        return (cliente or self.cliente_admin).get(reverse('financiero-buscar'), {'q': texto})

    def test_exige_autenticacion(self):
        self.assertEqual(self._buscar('estado', cliente_de(None)).status_code, 401)

    def test_encuentra_por_nombre_de_archivo_sin_importar_mayusculas(self):
        _documento(nombre='Balance-Octubre.pdf')
        _documento(nombre='otro.pdf')

        respuesta = self._buscar('balance')

        self.assertEqual([d['nombre_archivo'] for d in respuesta.data], ['Balance-Octubre.pdf'])

    def test_encuentra_por_nombre_de_financiera(self):
        _documento(nombre='a.pdf', financiera_id='001')
        _documento(nombre='b.pdf', financiera_id='002')

        respuesta = self._buscar('financiera b')

        self.assertEqual([d['nombre_archivo'] for d in respuesta.data], ['b.pdf'])

    def test_cada_resultado_trae_lo_necesario_para_abrirlo_en_estados_financieros(self):
        documento = _documento(nombre='septiembre.pdf', financiera_id='002', estado=Documento.RECHAZADO)

        resultado = self._buscar('septiembre').data[0]

        self.assertEqual(
            resultado,
            {
                'documento_id': documento.id,
                'nombre_archivo': 'septiembre.pdf',
                'estado': 'rechazado',
                'financiera_id': '002',
                'financiera_nombre': 'FINANCIERA B',
                'anio': 2026,
                'anio_numero': 2026,
                'mes_id': 10,
                'mes_nombre': 'Octubre',
                'corporacion_id': '001',
                'fecha': resultado['fecha'],
            },
        )

    def test_un_documento_sin_estado_cuenta_como_pendiente(self):
        _documento(nombre='nuevo.pdf', estado=None)

        self.assertEqual(self._buscar('nuevo').data[0]['estado'], 'pendiente')

    def test_quien_sube_solo_encuentra_lo_de_su_entidad(self):
        _documento(nombre='mio.pdf', financiera_id='001')
        _documento(nombre='ajeno.pdf', financiera_id='002')

        respuesta = self._buscar('.pdf', self.cliente_usuario)

        self.assertEqual([d['nombre_archivo'] for d in respuesta.data], ['mio.pdf'])

    def test_quien_consulta_encuentra_lo_de_todas(self):
        _documento(nombre='a.pdf', financiera_id='001')
        _documento(nombre='b.pdf', financiera_id='002')
        consulta = cliente_de(crear_usuario(rol_id=4, financiera_id='001'))

        self.assertEqual(len(self._buscar('.pdf', consulta).data), 2)

    def test_con_menos_de_dos_letras_no_busca(self):
        _documento(nombre='abc.pdf')

        self.assertEqual(self._buscar('a').data, [])
        self.assertEqual(self._buscar('  ').data, [])

    def test_sin_el_parametro_devuelve_una_lista_vacia(self):
        self.assertEqual(self.cliente_admin.get(reverse('financiero-buscar')).data, [])

    def test_trae_pocos_y_los_mas_recientes_primero(self):
        ahora = timezone.now()
        for numero in range(MAX_RESULTADOS_DE_BUSQUEDA + 3):
            _documento(nombre=f'estado-{numero}.pdf', fecha=ahora - timedelta(days=numero))

        nombres = [d['nombre_archivo'] for d in self._buscar('estado').data]

        self.assertEqual(len(nombres), MAX_RESULTADOS_DE_BUSQUEDA)
        self.assertEqual(nombres[0], 'estado-0.pdf')

    def test_un_comodin_de_sql_se_busca_como_texto(self):
        _documento(nombre='a.pdf')

        self.assertEqual(self._buscar('%%').data, [])
