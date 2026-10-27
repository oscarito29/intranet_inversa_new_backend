"""Qué hace cada rol con los estados financieros, y sobre qué entidades (principal y adicionales)."""

import shutil
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase, cliente_de, crear_usuario
from apps.financial.models import Documento, RangoFecha
from apps.usuarios.models import UsuarioEntidad

PDF = b'%PDF-1.4 contenido'
PERIODO = {'anio': 2026, 'mes': 10}
CARPETA_DE_ARCHIVOS = 'media_test_roles'  # `media_test*/` está en el .gitignore


@override_settings(MEDIA_ROOT=CARPETA_DE_ARCHIVOS)
class ConArchivos(ApiTestCase):
    """Las pruebas que suben archivos los guardan en una carpeta propia y la borran al terminar."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(shutil.rmtree, CARPETA_DE_ARCHIVOS, ignore_errors=True)


def _documento(financiera_id='001', corporacion_id='001', estado=Documento.PENDIENTE, sube='sube@inversa.hn', **extra) -> Documento:
    return Documento.objects.create(
        nombre_archivo=extra.pop('nombre_archivo', 'estado.pdf'),
        ruta_archivo='/media/documentos/estado.pdf',
        doc_aprobado=estado,
        anio_id=2026,
        mes_id=10,
        corporacion_id=corporacion_id,
        financiera_id=financiera_id,
        fecha=timezone.now(),
        email_usuario_sube=sube,
        **extra,
    )


def _abrir_ventana() -> None:
    hoy = timezone.localdate()
    RangoFecha.objects.create(desde=hoy - timedelta(days=1), hasta=hoy + timedelta(days=1), email_usuario='a@a.hn', fecha_modifica=timezone.now())


def _documentos(cliente, financiera, corporacion='001'):
    return cliente.get(reverse('financiero-documentos'), {**PERIODO, 'corporacion': corporacion, 'financiera': financiera})


def _periodo(cliente, corporacion='001'):
    return cliente.get(reverse('financiero-periodo'), {**PERIODO, 'corporacion': corporacion})


def _subir(cliente, financiera, corporacion='001'):
    datos = {'file': SimpleUploadedFile('estado.pdf', PDF), 'anio': 2026, 'mes_id': 10, 'corporacion_id': corporacion, 'financiera_id': financiera}
    return cliente.post(reverse('financiero-documentos'), datos, format='multipart')


class AprobadorTests(ConArchivos):
    def setUp(self):
        super().setUp()
        self.aprobador = crear_usuario(rol_id=3, financiera_id='001', email='aprobador@inversa.hn')
        self.cliente = cliente_de(self.aprobador)

    def test_ve_los_documentos_de_todas_las_entidades(self):
        _documento(financiera_id='002')

        respuesta = _documentos(self.cliente, '002')

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.data), 1)

    def test_ve_el_periodo_de_todas_las_financieras(self):
        filas = _periodo(self.cliente).data['financieras']

        self.assertEqual({fila['financiera_id'] for fila in filas}, {'001', '002'})

    def test_aprueba_rechaza_y_revoca_lo_que_subio_otra_persona(self):
        for accion, cuerpo in (('aprobar', None), ('rechazar', {'motivo': 'Ilegible'})):
            with self.subTest(accion=accion):
                documento = _documento()
                respuesta = self.cliente.post(reverse(f'financiero-{accion}', args=[documento.id]), cuerpo, format='json')
                self.assertEqual(respuesta.status_code, 200, respuesta.data)
        aprobado = _documento(estado=Documento.APROBADO)
        self.assertEqual(self.cliente.post(reverse('financiero-revocar', args=[aprobado.id]), {'motivo': 'Error'}, format='json').status_code, 200)

    def test_no_sube_documentos_ni_siquiera_a_su_propia_entidad(self):
        _abrir_ventana()

        self.assertEqual(_subir(self.cliente, '001').status_code, 403)

    def test_no_fija_la_ventana_de_subida(self):
        respuesta = self.cliente.post(reverse('financiero-rango-fechas'), {'desde': '2026-10-01', 'hasta': '2026-10-31'}, format='json')

        self.assertEqual(respuesta.status_code, 403)

    def test_la_campana_le_muestra_lo_pendiente_de_todas_las_entidades(self):
        _documento(financiera_id='001')
        _documento(financiera_id='002')

        datos = self.cliente.get(reverse('financiero-notificaciones')).data

        self.assertEqual((datos['total'], {item['financiera_id'] for item in datos['items']}), (2, {'001', '002'}))


class ConsultaTests(ConArchivos):
    def setUp(self):
        super().setUp()
        self.cliente = cliente_de(crear_usuario(rol_id=4, financiera_id='001', email='consulta@inversa.hn'))

    def test_ve_el_periodo_y_los_documentos_de_todas_las_entidades(self):
        _documento(financiera_id='002')

        self.assertEqual(len(_documentos(self.cliente, '002').data), 1)
        self.assertEqual({fila['financiera_id'] for fila in _periodo(self.cliente).data['financieras']}, {'001', '002'})

    def test_no_aprueba_rechaza_ni_revoca(self):
        documento = _documento()

        for accion in ('aprobar', 'rechazar', 'revocar'):
            with self.subTest(accion=accion):
                respuesta = self.cliente.post(reverse(f'financiero-{accion}', args=[documento.id]), {'motivo': 'x'}, format='json')
                self.assertEqual(respuesta.status_code, 403)
        documento.refresh_from_db()
        self.assertEqual(documento.doc_aprobado, Documento.PENDIENTE)

    def test_no_sube_documentos(self):
        _abrir_ventana()

        self.assertEqual(_subir(self.cliente, '001').status_code, 403)

    def test_no_tiene_avisos_en_la_campana(self):
        _documento(financiera_id='001', estado=Documento.RECHAZADO, fecha_rechaza=timezone.now(), motivo_rechazo='x')
        _documento(financiera_id='001')

        self.assertEqual(self.cliente.get(reverse('financiero-notificaciones')).data, {'total': 0, 'items': []})


class VariasEntidadesTests(ConArchivos):
    """La persona de la entidad 001 también trabaja para la 003 (que es de otra corporación)."""

    def setUp(self):
        super().setUp()
        UsuarioEntidad.objects.create(usuario=self.usuario, financiera_id='003')

    def test_ve_los_documentos_de_la_principal_y_de_la_adicional_pero_no_de_otra(self):
        _documento(financiera_id='001')
        _documento(financiera_id='003', corporacion_id='002')

        self.assertEqual(_documentos(self.cliente_usuario, '001').status_code, 200)
        self.assertEqual(_documentos(self.cliente_usuario, '003', '002').status_code, 200)
        self.assertEqual(_documentos(self.cliente_usuario, '002').status_code, 403)

    def test_el_periodo_trae_solo_sus_entidades_en_cada_corporacion(self):
        en_001 = _periodo(self.cliente_usuario, '001').data['financieras']
        en_002 = _periodo(self.cliente_usuario, '002').data['financieras']

        self.assertEqual([fila['financiera_id'] for fila in en_001], ['001'])
        self.assertEqual([fila['financiera_id'] for fila in en_002], ['003'])

    def test_sube_a_la_adicional_y_no_a_una_ajena(self):
        _abrir_ventana()

        self.assertEqual(_subir(self.cliente_usuario, '003', '002').status_code, 201)
        self.assertEqual(_subir(self.cliente_usuario, '002').status_code, 403)

    def test_la_campana_junta_lo_rechazado_de_todas_sus_entidades(self):
        ahora = timezone.now()
        _documento(financiera_id='001', estado=Documento.RECHAZADO, fecha_rechaza=ahora, motivo_rechazo='a')
        _documento(financiera_id='003', corporacion_id='002', estado=Documento.RECHAZADO, fecha_rechaza=ahora, motivo_rechazo='b')
        _documento(financiera_id='002', estado=Documento.RECHAZADO, fecha_rechaza=ahora, motivo_rechazo='ajeno')

        datos = self.cliente_usuario.get(reverse('financiero-notificaciones')).data

        self.assertEqual(sorted(item['financiera_id'] for item in datos['items']), ['001', '003'])

    def test_el_historial_de_un_documento_de_la_adicional_se_puede_ver(self):
        documento = _documento(financiera_id='003', corporacion_id='002')

        self.assertEqual(self.cliente_usuario.get(reverse('financiero-historial', args=[documento.id])).status_code, 200)

    def test_quitarle_la_adicional_le_quita_el_acceso(self):
        UsuarioEntidad.objects.filter(usuario=self.usuario).delete()

        self.assertEqual(_documentos(self.cliente_usuario, '003', '002').status_code, 403)

    def test_el_catalogo_le_dice_cuales_son_sus_entidades(self):
        acceso = self.cliente_usuario.get(reverse('financiero-catalogos')).data['usuario_acceso']

        self.assertEqual(acceso['financiera_ids'], ['001', '003'])
        self.assertEqual(acceso['financiera_id'], '001')


class NadieApruebaLoQueSubioTests(ConArchivos):
    def setUp(self):
        super().setUp()
        self.documento = _documento(sube=self.admin.email)

    def test_quien_subio_el_documento_no_lo_aprueba_rechaza_ni_revoca(self):
        revocable = _documento(sube=self.admin.email, estado=Documento.APROBADO)

        casos = (
            ('financiero-aprobar', self.documento, None),
            ('financiero-rechazar', self.documento, {'motivo': 'x'}),
            ('financiero-revocar', revocable, {'motivo': 'x'}),
        )
        for ruta, documento, cuerpo in casos:
            with self.subTest(ruta=ruta):
                respuesta = self.cliente_admin.post(reverse(ruta, args=[documento.id]), cuerpo, format='json')
                self.assertEqual(respuesta.status_code, 403)
                self.assertIn('subiste tú', respuesta.data['detail'])
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.doc_aprobado, Documento.PENDIENTE)

    def test_no_importa_como_este_escrito_el_correo(self):
        self.documento.email_usuario_sube = self.admin.email.upper()
        self.documento.save()

        self.assertEqual(self.cliente_admin.post(reverse('financiero-aprobar', args=[self.documento.id])).status_code, 403)

    def test_otra_persona_con_permiso_si_lo_aprueba(self):
        otro = cliente_de(crear_usuario(rol_id=1, email='otro.admin@inversa.hn'))

        self.assertEqual(otro.post(reverse('financiero-aprobar', args=[self.documento.id])).status_code, 200)

    def test_lo_que_sube_un_administrador_lo_aprueba_otro(self):
        _abrir_ventana()
        subido = _subir(self.cliente_admin, '001')
        self.assertEqual(subido.status_code, 201, subido.data)

        propio = self.cliente_admin.post(reverse('financiero-aprobar', args=[subido.data['id']]))
        ajeno = cliente_de(crear_usuario(rol_id=3, email='aprobador@inversa.hn')).post(reverse('financiero-aprobar', args=[subido.data['id']]))

        self.assertEqual((propio.status_code, ajeno.status_code), (403, 200))
