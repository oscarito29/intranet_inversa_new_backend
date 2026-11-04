"""
Consultas por petición: el número no debe crecer con las filas (consultas N+1).

Cada prueba pide una lista con pocas filas y otra vez con muchas más y compara cuántas consultas a la base hizo.
Si alguien agrega un campo a un serializer que consulta por fila, la cifra sube y la prueba falla.
"""

from datetime import date, time

from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.configuracion.models import Actividad, Comunicado, Imagen
from apps.core.testing import ApiTestCase, crear_usuario
from apps.documentos.models import Category, DocsEtiqueta, Etiqueta, EtiquetaRol, Upload
from apps.financial.models import Documento

POCAS = 2
MUCHAS = 14


def _consultas(cliente, nombre: str, **parametros) -> int:
    cache.clear()  # los catálogos se guardan en caché; se mide lo que cuesta pedirlos de cero
    with CaptureQueriesContext(connection) as captura:
        respuesta = cliente.get(reverse(nombre), parametros)
    assert respuesta.status_code == 200, (nombre, respuesta.status_code, getattr(respuesta, 'data', None))
    return len(captura)


class ConsultasNoCrecenConLasFilasTests(ApiTestCase):
    def _comparar(self, cliente, nombre: str, crear, **parametros) -> None:
        """`crear(indice)` agrega una fila de ese recurso."""
        for indice in range(POCAS):
            crear(indice)
        con_pocas = _consultas(cliente, nombre, **parametros)
        for indice in range(POCAS, MUCHAS):
            crear(indice)
        con_muchas = _consultas(cliente, nombre, **parametros)

        self.assertEqual(con_muchas, con_pocas, f'{nombre}: {con_pocas} consultas con {POCAS} filas y {con_muchas} con {MUCHAS}')

    # ---- documentos institucionales
    def _documento_con_etiqueta_y_version(self, categoria, etiqueta):
        def crear(indice):
            anterior = Upload.objects.create(fname=f'/media/v{indice}.pdf', name=f'v{indice}.pdf', area=categoria, estado=Upload.REEMPLAZADO, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB')
            actual = Upload.objects.create(fname=f'/media/d{indice}.pdf', name=f'd{indice}.pdf', area=categoria, estado=Upload.ACTIVO, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB', reemplaza_a=anterior)
            DocsEtiqueta.objects.create(documento=actual, etiqueta=etiqueta)

        return crear

    def _escenario_de_documentos(self):
        categoria = Category.objects.create(name='Contabilidad', description='x', created_at=timezone.now())
        etiqueta = Etiqueta.objects.create(etiqueta_nombre='General')
        EtiquetaRol.objects.create(etiqueta=etiqueta, rol_id=2)
        EtiquetaRol.objects.create(etiqueta=etiqueta, rol_id=1)
        return self._documento_con_etiqueta_y_version(categoria, etiqueta)

    def test_lista_de_documentos_con_etiquetas_y_versiones(self):
        self._comparar(self.cliente_usuario, 'documentos-documentos', self._escenario_de_documentos())

    def test_mapa_de_etiquetas_por_documento(self):
        self._comparar(self.cliente_usuario, 'documentos-docs-etiquetas', self._escenario_de_documentos())

    def test_exportar_documentos(self):
        self._comparar(self.cliente_usuario, 'documentos-exportar', self._escenario_de_documentos())

    def test_categorias_con_su_conteo(self):
        self._comparar(self.cliente_usuario, 'documentos-categorias', lambda i: Category.objects.create(name=f'Cat {i}', description='x', created_at=timezone.now()))

    # ---- estados financieros
    def _documento_financiero(self, indice):
        Documento.objects.create(
            nombre_archivo=f'estado{indice}.pdf', ruta_archivo='/media/a.pdf', doc_aprobado='', anio_id=2026, mes_id=10,
            corporacion_id='001', financiera_id='001', fecha=timezone.now(), email_usuario_sube='x@inversa.hn',
        )

    def test_documentos_financieros_de_una_financiera(self):
        parametros = {'anio': 2026, 'mes': 10, 'corporacion': '001', 'financiera': '001'}

        self._comparar(self.cliente_usuario, 'financiero-documentos', self._documento_financiero, **parametros)

    def test_estado_del_periodo_por_financiera(self):
        self._comparar(self.cliente_admin, 'financiero-periodo', self._documento_financiero, anio=2026, mes=10, corporacion='001')

    def test_notificaciones_del_administrador(self):
        self._comparar(self.cliente_admin, 'financiero-notificaciones', self._documento_financiero)

    # ---- personas
    def test_lista_de_usuarios_del_administrador(self):
        self._comparar(self.cliente_admin, 'usuarios-list-create', lambda i: crear_usuario(name=f'persona{i}'))

    def test_directorio(self):
        self._comparar(self.cliente_usuario, 'usuarios-directorio', lambda i: crear_usuario(name=f'persona{i}', financiera_id='002' if i % 2 else '001'))

    def test_cumpleanos_del_mes(self):
        hoy = timezone.localdate()
        self._comparar(self.cliente_usuario, 'configuracion-cumpleanos', lambda i: crear_usuario(name=f'persona{i}', fecha_nacimiento=date(1990, hoy.month, 1 + i % 27)))

    # ---- configuración
    def test_comunicados(self):
        self._comparar(
            self.cliente_usuario, 'configuracion-comunicados',
            lambda i: Comunicado.objects.create(titulo=f'c{i}', contenido='x', imagen='/media/a.png', usuario_sube='a@inversa.hn', fecha_subida=date.today()),
        )

    def test_imagenes_del_carrusel(self):
        self._comparar(self.cliente_usuario, 'configuracion-imagenes', lambda i: Imagen.objects.create(archivo=f'a{i}.png', ruta_img='/media/a.png', puesto=i % 4 + 1, creado_en=timezone.now()))

    def test_actividades(self):
        self._comparar(
            self.cliente_usuario, 'configuracion-actividades',
            lambda i: Actividad.objects.create(fecha=date(2026, 11, 1 + i % 27), titulo=f'a{i}', descripcion='x', hora_desde=time(9, 0), hora_hasta=time(10, 0)),
        )

    def test_etiquetas_y_los_roles_que_las_ven(self):
        def crear(indice):
            etiqueta = Etiqueta.objects.create(etiqueta_nombre=f'e{indice}')
            EtiquetaRol.objects.create(etiqueta=etiqueta, rol_id=1)
            EtiquetaRol.objects.create(etiqueta=etiqueta, rol_id=2)

        self._comparar(self.cliente_usuario, 'configuracion-etiquetas', crear)
        self._comparar(self.cliente_usuario, 'configuracion-etiqueta-roles', lambda i: None)


class UnaConsultaNoPasaDeUnTopeTests(ApiTestCase):
    """Cotas absolutas: una pantalla no debería necesitar decenas de consultas ni con pocos datos."""

    def test_ninguna_lista_principal_pasa_de_diez_consultas(self):
        categoria = Category.objects.create(name='Contabilidad', description='x', created_at=timezone.now())
        Upload.objects.create(fname='/media/d.pdf', name='d.pdf', area=categoria, estado=Upload.ACTIVO, fecha=timezone.now(), tipo='application/pdf', tamanio='1 KB')
        for nombre, parametros in (
            ('documentos-documentos', {}),
            ('documentos-categorias', {}),
            ('usuarios-directorio', {}),
            ('financiero-catalogos', {}),
            ('financiero-resumen', {}),
            ('financiero-notificaciones', {}),
            ('configuracion-bitacora', {}),
        ):
            with self.subTest(ruta=nombre):
                cliente = self.cliente_admin
                self.assertLessEqual(_consultas(cliente, nombre, **parametros), 10)
