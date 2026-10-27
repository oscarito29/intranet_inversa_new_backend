import io
import shutil
import zipfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.core.subidas import tipo_mime_de, validar_contenido
from apps.core.testing import ApiTestCase
from apps.financial.models import RangoFecha

PDF = b'%PDF-1.4\n%contenido'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16
JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 16
WEBP = b'RIFF\x24\x00\x00\x00WEBPVP8 '
OLE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 16
RAR = b'Rar!\x1a\x07\x00' + b'\x00' * 8
HTML = b'<html><script>alert(1)</script></html>'
EJECUTABLE = b'MZ\x90\x00\x03\x00\x00\x00'


def _zip(entradas: dict[str, bytes]) -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, 'w') as comprimido:
        for nombre, contenido in entradas.items():
            comprimido.writestr(nombre, contenido)
    return salida.getvalue()


DOCX = _zip({'[Content_Types].xml': b'<Types/>', 'word/document.xml': b'<w/>'})
XLSX = _zip({'[Content_Types].xml': b'<Types/>', 'xl/workbook.xml': b'<w/>'})


def _archivo(nombre: str, contenido: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(nombre, contenido)


class ValidarContenidoTests(SimpleTestCase):
    def test_acepta_cada_formato_cuando_el_contenido_coincide(self):
        casos = {
            'a.pdf': PDF,
            'a.png': PNG,
            'a.jpg': JPG,
            'a.jpeg': JPG,
            'a.webp': WEBP,
            'a.doc': OLE,
            'a.xls': OLE,
            'a.rar': RAR,
            'a.docx': DOCX,
            'a.xlsx': XLSX,
            'a.txt': 'Hola, año nuevo'.encode(),
        }
        for nombre, contenido in casos.items():
            with self.subTest(nombre=nombre):
                validar_contenido(_archivo(nombre, contenido))

    def test_una_pagina_con_scripts_disfrazada_de_pdf_se_rechaza(self):
        with self.assertRaisesMessage(ValidationError, 'no corresponde a su extensión (.pdf)'):
            validar_contenido(_archivo('balance.pdf', HTML))

    def test_un_ejecutable_disfrazado_se_rechaza_en_cualquier_extension(self):
        for nombre in ('a.pdf', 'a.png', 'a.docx', 'a.xls', 'a.rar', 'a.txt'):
            with self.subTest(nombre=nombre), self.assertRaises(ValidationError):
                validar_contenido(_archivo(nombre, EJECUTABLE + b'\x00' * 8))

    def test_un_formato_con_la_extension_de_otro_se_rechaza(self):
        with self.assertRaises(ValidationError):
            validar_contenido(_archivo('foto.png', PDF))
        with self.assertRaises(ValidationError):
            validar_contenido(_archivo('doc.pdf', PNG))

    def test_un_zip_cualquiera_no_es_un_docx_ni_un_xlsx(self):
        otro = _zip({'cualquier.txt': b'x'})

        with self.assertRaises(ValidationError):
            validar_contenido(_archivo('a.docx', otro))
        with self.assertRaises(ValidationError):
            validar_contenido(_archivo('a.xlsx', DOCX))
        with self.assertRaises(ValidationError):
            validar_contenido(_archivo('a.docx', b'PK\x03\x04roto'))

    def test_un_riff_que_no_es_webp_se_rechaza(self):
        with self.assertRaises(ValidationError):
            validar_contenido(_archivo('a.webp', b'RIFF\x24\x00\x00\x00WAVEfmt '))

    def test_un_txt_con_bytes_nulos_es_un_binario(self):
        with self.assertRaises(ValidationError):
            validar_contenido(_archivo('nota.txt', b'hola\x00\x01\x02'))

    def test_un_archivo_vacio_se_rechaza(self):
        with self.assertRaisesMessage(ValidationError, 'vacío'):
            validar_contenido(_archivo('a.pdf', b''))

    def test_una_extension_no_permitida_se_rechaza(self):
        for nombre in ('virus.exe', 'pagina.html', 'imagen.svg', 'sin_extension', 'script.php'):
            with self.subTest(nombre=nombre), self.assertRaises(ValidationError):
                validar_contenido(_archivo(nombre, PDF))

    def test_la_extension_no_distingue_mayusculas(self):
        validar_contenido(_archivo('BALANCE.PDF', PDF))

    def test_deja_el_archivo_listo_para_guardarse(self):
        archivo = _archivo('a.pdf', PDF)

        validar_contenido(archivo)

        self.assertEqual(archivo.read(), PDF)


class TipoMimeTests(SimpleTestCase):
    def test_sale_de_la_extension_y_no_de_lo_que_diga_el_navegador(self):
        self.assertEqual(tipo_mime_de('balance.pdf'), 'application/pdf')
        self.assertEqual(tipo_mime_de('hoja.XLSX'), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_sin_extension_conocida_es_el_generico(self):
        self.assertEqual(tipo_mime_de('raro.zzz'), 'application/octet-stream')
        self.assertEqual(tipo_mime_de(None), 'application/octet-stream')


@override_settings(MEDIA_ROOT='media_test_subidas')
class VíasDeSubidaTests(ApiTestCase):
    """Cada vía que recibe un archivo rechaza el que no es lo que dice ser."""

    def tearDown(self):
        shutil.rmtree('media_test_subidas', ignore_errors=True)

    def test_la_foto_de_perfil_rechaza_un_pdf_con_extension_png(self):
        respuesta = self.cliente_usuario.post(reverse('perfil-foto'), {'picture': _archivo('foto.png', PDF)}, format='multipart')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('picture', respuesta.data)

    def test_la_foto_de_perfil_acepta_una_imagen_real(self):
        respuesta = self.cliente_usuario.post(reverse('perfil-foto'), {'picture': _archivo('foto.png', PNG)}, format='multipart')

        self.assertEqual(respuesta.status_code, 200)

    def test_una_imagen_del_carrusel_rechaza_un_html_con_extension_png(self):
        respuesta = self.cliente_admin.post(reverse('configuracion-imagenes'), {'file': _archivo('a.png', HTML)}, format='multipart')

        self.assertEqual(respuesta.status_code, 400)

    def test_la_imagen_de_un_comunicado_rechaza_un_ejecutable(self):
        datos = {'titulo': 't', 'contenido': 'c', 'file': _archivo('a.jpg', EJECUTABLE)}

        self.assertEqual(self.cliente_admin.post(reverse('configuracion-comunicados'), datos, format='multipart').status_code, 400)

    def test_un_documento_institucional_rechaza_un_html_con_extension_pdf(self):
        from apps.documentos.tests.test_documentos import _categoria

        categoria = _categoria()
        datos = {'name': 'Balance', 'area': categoria.id, 'file': _archivo('balance.pdf', HTML)}

        respuesta = self.cliente_admin.post(reverse('documentos-documentos'), datos, format='multipart')

        self.assertEqual(respuesta.status_code, 400)

    def test_un_documento_institucional_guarda_el_tipo_segun_la_extension_y_no_el_encabezado(self):
        from apps.documentos.models import Upload
        from apps.documentos.tests.test_documentos import _categoria

        categoria = _categoria()
        archivo = SimpleUploadedFile('balance.pdf', PDF, content_type='text/html')

        self.cliente_admin.post(reverse('documentos-documentos'), {'name': 'Balance', 'area': categoria.id, 'file': archivo}, format='multipart')

        self.assertEqual(Upload.objects.get(name='Balance').tipo, 'application/pdf')

    def test_un_estado_financiero_rechaza_un_ejecutable_con_extension_pdf(self):
        from datetime import timedelta

        from django.utils import timezone

        hoy = timezone.localdate()
        RangoFecha.objects.create(desde=hoy - timedelta(days=1), hasta=hoy + timedelta(days=1), email_usuario='a@inversa.hn', fecha_modifica=timezone.now())
        datos = {'file': _archivo('estado.pdf', EJECUTABLE), 'anio': 2026, 'mes_id': 10, 'corporacion_id': '001', 'financiera_id': '001'}

        respuesta = self.cliente_usuario.post(reverse('financiero-documentos'), datos, format='multipart')

        self.assertEqual(respuesta.status_code, 400)
