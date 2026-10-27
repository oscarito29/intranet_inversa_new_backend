from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase, crear_usuario
from apps.documentos.tests.test_documentos import _categoria, _documento
from apps.financial.models import Bitacora, Documento


def _descripciones(accion: str = 'Edicion') -> list[str]:
    return list(Bitacora.objects.filter(accion=accion).values_list('descripcion', flat=True))


class CambiosSensiblesDeUnUsuarioTests(ApiTestCase):
    def _editar(self, persona, **cambios):
        return self.cliente_admin.patch(reverse('usuarios-detail', args=[persona.pk]), cambios, format='json')

    def test_cambiar_el_rol_deja_su_propio_renglon_con_el_rol_anterior_y_el_nuevo(self):
        persona = crear_usuario(email='persona@inversa.hn', rol_id=2)

        self._editar(persona, rol_id=1)

        self.assertIn('Cambio de rol de persona@inversa.hn: User a Admin', _descripciones())

    def test_cambiar_la_entidad_deja_su_propio_renglon(self):
        persona = crear_usuario(email='persona@inversa.hn', financiera_id='001')

        self._editar(persona, userFinancieraId='002')

        self.assertIn('Cambio de entidad de persona@inversa.hn: 001 a 002', _descripciones())

    def test_desactivar_y_activar_dejan_su_propio_renglon(self):
        persona = crear_usuario(email='persona@inversa.hn')

        self._editar(persona, estado='I')
        self._editar(persona, estado='A')

        self.assertIn('Desactiva al usuario persona@inversa.hn', _descripciones())
        self.assertIn('Activa al usuario persona@inversa.hn', _descripciones())

    def test_editar_solo_el_nombre_no_deja_renglones_de_cambios_sensibles(self):
        persona = crear_usuario(email='persona@inversa.hn')

        self._editar(persona, name='Otro nombre')

        descripciones = ' | '.join(_descripciones())
        self.assertIn('Modifica el usuario persona@inversa.hn', descripciones)
        self.assertNotIn('Cambio de rol', descripciones)
        self.assertNotIn('Cambio de entidad', descripciones)
        self.assertNotIn('Activa', descripciones)

    def test_los_renglones_quedan_a_nombre_de_quien_hizo_el_cambio(self):
        persona = crear_usuario(email='persona@inversa.hn', rol_id=2)

        self._editar(persona, rol_id=1)

        self.assertTrue(Bitacora.objects.filter(descripcion__startswith='Cambio de rol', usuario=self.admin.email).exists())


class ExportacionesAuditadasTests(ApiTestCase):
    def test_exportar_el_periodo_queda_en_la_bitacora(self):
        Documento.objects.create(
            nombre_archivo='a.pdf', ruta_archivo='/media/a.pdf', doc_aprobado='', anio_id=2026, mes_id=10,
            corporacion_id='001', financiera_id='001', fecha=timezone.now(), email_usuario_sube='x@inversa.hn',
        )

        self.cliente_admin.get(reverse('financiero-exportar'), {'anio': 2026, 'mes': 10, 'corporacion': '001'})

        self.assertEqual(_descripciones('Exportacion'), ['Exporta a Excel el periodo 10/2026 de la corporacion 001'])
        self.assertTrue(Bitacora.objects.filter(accion='Exportacion', usuario=self.admin.email).exists())

    def test_exportar_documentos_queda_en_la_bitacora_con_la_cantidad(self):
        categoria = _categoria()
        _documento(categoria, nombre='a.pdf')
        _documento(categoria, nombre='b.pdf')

        self.cliente_usuario.get(reverse('documentos-exportar'))

        self.assertEqual(_descripciones('Exportacion'), ['Exporta a Excel 2 documentos institucionales'])
        self.assertTrue(Bitacora.objects.filter(accion='Exportacion', usuario=self.usuario.email).exists())

    def test_una_exportacion_que_falla_no_deja_renglon(self):
        self.cliente_admin.get(reverse('financiero-exportar'), {'anio': 2026, 'mes': 13, 'corporacion': '001'})

        self.assertEqual(_descripciones('Exportacion'), [])
