import zipfile
from io import BytesIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase, cliente_de, crear_usuario
from apps.financial.models import Bitacora, Documento

PERIODO = {'anio': 2026, 'mes': 10, 'corporacion': '001'}
BUCKET_ANTERIOR = 'https://bucket-anterior.s3.amazonaws.com/documentos/viejo.pdf'


class ExportarZipTests(ApiTestCase):
    def _guardar(self, clave: str, contenido: bytes) -> str:
        nombre = default_storage.save(clave, ContentFile(contenido))
        self.addCleanup(default_storage.delete, nombre)
        return f'storage:{nombre}'

    def _documento(self, estado=Documento.APROBADO, financiera_id='001', nombre='estado.pdf', contenido=b'%PDF-1.4 contenido', ruta=None):
        return Documento.objects.create(
            nombre_archivo=nombre,
            ruta_archivo=ruta or self._guardar(f'documentos/prueba-zip/{financiera_id}.pdf', contenido),
            doc_aprobado=estado,
            anio_id=2026,
            mes_id=10,
            corporacion_id='001',
            financiera_id=financiera_id,
            fecha=timezone.now(),
            email_usuario_sube='sube@inversa.hn',
        )

    def _descargar(self, cliente=None, **parametros):
        return (cliente or self.cliente_admin).get(reverse('financiero-exportar-zip'), {**PERIODO, **parametros})

    def _zip(self, respuesta) -> zipfile.ZipFile:
        return zipfile.ZipFile(BytesIO(b''.join(respuesta.streaming_content)))

    def test_exige_autenticacion(self):
        self.assertEqual(self._descargar(cliente_de(None)).status_code, 401)

    def test_quien_no_puede_exportar_no_descarga(self):
        self._documento()

        self.assertEqual(self._descargar(self.cliente_usuario).status_code, 403)

    def test_descarga_un_zip_con_nombre_que_dice_el_periodo(self):
        self._documento()

        respuesta = self._descargar()

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/zip')
        self.assertIn('documentos-2026-10-corporacion-001.zip', respuesta['Content-Disposition'])

    def test_trae_el_documento_de_cada_financiera_con_su_estado_en_el_nombre(self):
        self._documento(estado=Documento.APROBADO, financiera_id='001', nombre='a.pdf', contenido=b'contenido-a')
        self._documento(estado=Documento.PENDIENTE, financiera_id='002', nombre='b.pdf', contenido=b'contenido-b')

        archivos = self._zip(self._descargar())

        self.assertEqual(sorted(archivos.namelist()), ['FINANCIERA A - aprobado - a.pdf', 'FINANCIERA B - pendiente - b.pdf'])
        self.assertEqual(archivos.read('FINANCIERA A - aprobado - a.pdf'), b'contenido-a')

    def test_no_incluye_rechazados_ni_revocados(self):
        self._documento(estado=Documento.APROBADO, financiera_id='001', nombre='a.pdf')
        self._documento(estado=Documento.RECHAZADO, financiera_id='002', nombre='b.pdf')

        self.assertEqual(self._zip(self._descargar()).namelist(), ['FINANCIERA A - aprobado - a.pdf'])

    def test_un_nombre_con_barras_no_sale_del_zip(self):
        self._documento(nombre='../../etc/pasa.pdf')

        nombres = self._zip(self._descargar()).namelist()

        self.assertEqual(len(nombres), 1)
        self.assertNotIn('/', nombres[0])
        self.assertNotIn('\\', nombres[0])

    def test_lo_que_esta_en_el_bucket_anterior_no_entra_y_se_anota_en_un_leeme(self):
        self._documento(financiera_id='001', nombre='a.pdf')
        self._documento(financiera_id='002', nombre='viejo.pdf', ruta=BUCKET_ANTERIOR)

        archivos = self._zip(self._descargar())

        self.assertEqual(sorted(archivos.namelist()), ['FINANCIERA A - aprobado - a.pdf', 'LEEME.txt'])
        self.assertIn('FINANCIERA B: viejo.pdf', archivos.read('LEEME.txt').decode())

    def test_si_ningun_archivo_se_puede_leer_avisa_en_vez_de_dar_un_zip_vacio(self):
        self._documento(nombre='viejo.pdf', ruta=BUCKET_ANTERIOR)

        respuesta = self._descargar()

        self.assertEqual(respuesta.status_code, 400)

    def test_sin_documentos_vigentes_avisa(self):
        self._documento(estado=Documento.REVOCADO)

        self.assertEqual(self._descargar().status_code, 400)

    def test_si_el_periodo_pesa_demasiado_no_se_arma(self):
        self._documento(contenido=b'x' * 100)

        with patch('apps.financial.services.LIMITE_DEL_ZIP_BYTES', 50):
            respuesta = self._descargar()

        self.assertEqual(respuesta.status_code, 400)

    def test_deja_constancia_en_la_bitacora(self):
        self._documento()

        self._descargar()

        entrada = Bitacora.objects.get(accion='Exportacion')
        self.assertEqual(entrada.usuario, 'admin@inversa.hn')
        self.assertIn('ZIP', entrada.descripcion)

    def test_quien_consulta_descarga_lo_de_todas_las_financieras(self):
        self._documento(financiera_id='001', nombre='a.pdf')
        self._documento(financiera_id='002', nombre='b.pdf')
        consulta = cliente_de(crear_usuario(rol_id=4, financiera_id='001'))

        self.assertEqual(len(self._zip(self._descargar(consulta)).namelist()), 2)

    def test_pide_un_periodo_valido(self):
        self.assertEqual(self._descargar(anio=1900).status_code, 400)
