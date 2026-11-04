from datetime import date

from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase, cliente_de, crear_usuario
from apps.usuarios.selectors import DIRECTORIO_MAXIMO


class DirectorioTests(ApiTestCase):
    def _pedir(self, cliente=None, **parametros):
        return (cliente or self.cliente_usuario).get(reverse('usuarios-directorio'), parametros)

    def _nombres(self, cliente=None, **parametros) -> list[str]:
        return [persona['name'] for persona in self._pedir(cliente, **parametros).data['personas']]

    def test_exige_autenticacion(self):
        self.assertEqual(self._pedir(cliente_de(None)).status_code, 401)

    def test_un_usuario_normal_puede_verlo(self):
        respuesta = self._pedir(self.cliente_usuario)

        self.assertEqual(respuesta.status_code, 200)
        self.assertGreaterEqual(respuesta.data['total'], 2)

    def test_cada_persona_trae_solo_los_datos_de_contacto(self):
        persona = self._pedir().data['personas'][0]

        self.assertEqual(set(persona), {'id', 'name', 'email', 'telefono', 'entidad', 'corporacion', 'foto', 'cumple_dia', 'cumple_mes'})

    def test_no_expone_direccion_ni_el_anio_de_nacimiento_ni_el_rol(self):
        crear_usuario(name='Ana', fecha_nacimiento=date(1990, 3, 14))

        respuesta = self._pedir(q='Ana').data
        texto = str(respuesta)

        self.assertEqual(len(respuesta['personas']), 1)
        self.assertNotIn('Dirección', texto)
        self.assertNotIn('1990', texto)
        self.assertNotIn('rol', ' '.join(respuesta['personas'][0]))
        self.assertNotIn('address', respuesta['personas'][0])
        self.assertNotIn('fecha_nacimiento', respuesta['personas'][0])

    def test_el_cumpleanos_sale_como_dia_y_mes(self):
        crear_usuario(name='Ana', fecha_nacimiento=date(1990, 3, 14))
        crear_usuario(name='Luis', fecha_nacimiento=None)

        ana = self._pedir(q='Ana').data['personas'][0]
        luis = self._pedir(q='Luis').data['personas'][0]

        self.assertEqual((ana['cumple_dia'], ana['cumple_mes']), (14, 3))
        self.assertEqual((luis['cumple_dia'], luis['cumple_mes']), (None, None))

    def test_trae_la_entidad_y_su_corporacion(self):
        crear_usuario(name='Ana', financiera_id='002')

        ana = self._pedir(q='Ana').data['personas'][0]

        self.assertEqual((ana['entidad'], ana['corporacion']), ('FINANCIERA B', 'FINANCIERAS'))

    def test_no_muestra_a_los_inactivos_ni_a_los_dados_de_baja(self):
        crear_usuario(name='Inactivo', estado='I')
        crear_usuario(name='Baja', deleted_at=timezone.now())

        nombres = self._nombres()

        self.assertNotIn('Inactivo', nombres)
        self.assertNotIn('Baja', nombres)

    def test_busca_por_nombre_correo_o_entidad_sin_distinguir_mayusculas(self):
        crear_usuario(name='Maria', email='maria@inversa.hn', financiera_id='001')
        crear_usuario(name='Pedro', email='pedro@otra.hn', financiera_id='002')

        self.assertIn('Maria', self._nombres(q='MARIA'))
        self.assertEqual(self._nombres(q='pedro@otra'), ['Pedro'])
        self.assertIn('Pedro', self._nombres(q='financiera b'))
        self.assertNotIn('Maria', self._nombres(q='financiera b'))

    def test_filtra_por_entidad(self):
        crear_usuario(name='Pedro', financiera_id='002')

        nombres = self._nombres(entidad='002')

        self.assertEqual(nombres, ['Pedro'])

    def test_va_ordenado_por_nombre(self):
        crear_usuario(name='Zoe')
        crear_usuario(name='Abel')

        nombres = self._nombres()

        self.assertEqual(nombres, sorted(nombres))

    def test_con_mas_de_lo_permitido_trae_el_maximo_pero_cuenta_todas(self):
        for numero in range(DIRECTORIO_MAXIMO + 3):
            crear_usuario(name=f'persona{numero:03d}')

        respuesta = self._pedir().data

        self.assertEqual(len(respuesta['personas']), DIRECTORIO_MAXIMO)
        self.assertGreaterEqual(respuesta['total'], DIRECTORIO_MAXIMO + 3)

    def test_las_consultas_no_crecen_con_las_personas(self):
        self._pedir()
        with self.assertNumQueries(2):
            self._pedir()
        for numero in range(8):
            crear_usuario(name=f'extra{numero}', financiera_id='002' if numero % 2 else '001')
        with self.assertNumQueries(2):
            self._pedir()
