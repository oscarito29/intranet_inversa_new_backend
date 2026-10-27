import shutil
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import ApiTestCase, crear_usuario, cliente_de
from apps.financial.models import Anio, Bitacora, Documento, RangoFecha

PARAMETROS = {'anio': 2026, 'mes': 10, 'corporacion': '001', 'financiera': '001'}


def _crear_documento(estado=Documento.PENDIENTE, financiera_id='001', corporacion_id='001') -> Documento:
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


def _abrir_ventana_de_subida(dias_antes=1, dias_despues=1) -> None:
    hoy = timezone.localdate()
    RangoFecha.objects.create(
        desde=hoy - timedelta(days=dias_antes),
        hasta=hoy + timedelta(days=dias_despues),
        email_usuario='admin@inversa.hn',
        fecha_modifica=timezone.now(),
    )


class PermisosPorFinancieraTests(ApiTestCase):
    def test_usuario_ve_documentos_de_su_financiera(self):
        _crear_documento(financiera_id='001')

        respuesta = self.cliente_usuario.get(reverse('financiero-documentos'), PARAMETROS)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.data), 1)

    def test_usuario_no_ve_documentos_de_otra_financiera(self):
        respuesta = self.cliente_usuario.get(reverse('financiero-documentos'), {**PARAMETROS, 'financiera': '002'})

        self.assertEqual(respuesta.status_code, 403)

    def test_admin_ve_cualquier_financiera(self):
        respuesta = self.cliente_admin.get(reverse('financiero-documentos'), {**PARAMETROS, 'financiera': '002'})

        self.assertEqual(respuesta.status_code, 200)

    def test_usuario_no_puede_subir_a_otra_financiera(self):
        _abrir_ventana_de_subida()
        archivo = SimpleUploadedFile('estado.pdf', b'%PDF-1.4', content_type='application/pdf')

        respuesta = self.cliente_usuario.post(
            reverse('financiero-documentos'),
            {'file': archivo, 'anio': 2026, 'mes_id': 10, 'corporacion_id': '001', 'financiera_id': '002'},
            format='multipart',
        )

        self.assertEqual(respuesta.status_code, 403)

    def test_solo_admin_aprueba_rechaza_revoca_o_fija_el_rango(self):
        documento = _crear_documento()
        for nombre, argumentos in (
            ('financiero-aprobar', [documento.id]),
            ('financiero-rechazar', [documento.id]),
            ('financiero-revocar', [documento.id]),
            ('financiero-rango-fechas', []),
        ):
            respuesta = self.cliente_usuario.post(reverse(nombre, args=argumentos), {'motivo': 'x'}, format='json')
            self.assertEqual(respuesta.status_code, 403, nombre)


class ValidacionDeParametrosTests(ApiTestCase):
    def test_anio_no_numerico_es_400_no_500(self):
        respuesta = self.cliente_admin.get(reverse('financiero-documentos'), {**PARAMETROS, 'anio': 'abc'})

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('anio', respuesta.data)

    def test_faltan_parametros(self):
        self.assertEqual(self.cliente_admin.get(reverse('financiero-documentos')).status_code, 400)

    def test_mes_inexistente(self):
        respuesta = self.cliente_admin.get(reverse('financiero-documentos'), {**PARAMETROS, 'mes': 13})

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('mes', respuesta.data)

    def test_financiera_de_otra_corporacion(self):
        respuesta = self.cliente_admin.get(reverse('financiero-documentos'), {**PARAMETROS, 'financiera': '003'})

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('financiera', respuesta.data)


@override_settings(MEDIA_ROOT='media_test_financiero')
class SubidaYVentanaTests(ApiTestCase):
    def tearDown(self):
        shutil.rmtree('media_test_financiero', ignore_errors=True)

    def _subir(self, cliente=None, nombre='estado.pdf', **extra):
        datos = {
            'file': SimpleUploadedFile(nombre, b'%PDF-1.4', content_type='application/pdf'),
            'anio': 2026,
            'mes_id': 10,
            'corporacion_id': '001',
            'financiera_id': '001',
            **extra,
        }
        return (cliente or self.cliente_usuario).post(reverse('financiero-documentos'), datos, format='multipart')

    def test_sin_rango_vigente_no_se_puede_subir(self):
        respuesta = self._subir()

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['detail'], 'La subida de documentos no está habilitada en esta fecha.')

    def test_rango_vencido_no_permite_subir_ni_siquiera_a_un_admin(self):
        hoy = timezone.localdate()
        RangoFecha.objects.create(
            desde=hoy - timedelta(days=10), hasta=hoy - timedelta(days=1), email_usuario='a@a.hn', fecha_modifica=timezone.now()
        )

        self.assertEqual(self._subir(self.cliente_admin).status_code, 400)

    def test_dentro_del_rango_sube_y_queda_pendiente_con_bitacora(self):
        _abrir_ventana_de_subida()

        respuesta = self._subir()

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data['doc_aprobado'], Documento.PENDIENTE)
        self.assertEqual(respuesta.data['email_usuario_sube'], self.usuario.email)
        self.assertTrue(Bitacora.objects.filter(usuario=self.usuario.email, accion='Creacion').exists())

    def test_extension_no_permitida(self):
        _abrir_ventana_de_subida()

        respuesta = self._subir(nombre='virus.exe')

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(Documento.objects.count(), 0)

    def test_guardar_rango_con_fechas_invertidas(self):
        respuesta = self.cliente_admin.post(reverse('financiero-rango-fechas'), {'desde': '2026-10-10', 'hasta': '2026-10-01'}, format='json')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('hasta', respuesta.data)


class MaquinaDeEstadosTests(ApiTestCase):
    def _accion(self, nombre, documento_id, motivo='Motivo de prueba'):
        return self.cliente_admin.post(reverse(nombre, args=[documento_id]), {'motivo': motivo}, format='json')

    def test_pendiente_se_aprueba_y_envia_correo_al_confirmar(self):
        documento = _crear_documento()

        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self._accion('financiero-aprobar', documento.id)

        self.assertEqual(respuesta.status_code, 200)
        documento.refresh_from_db()
        self.assertEqual(documento.doc_aprobado, Documento.APROBADO)
        self.assertEqual(documento.email_usuario_aprueba, self.admin.email)
        self.assertEqual(len(mail.outbox), 1)

    def test_el_correo_no_sale_si_la_transaccion_no_se_confirma(self):
        documento = _crear_documento()

        self._accion('financiero-aprobar', documento.id)

        self.assertEqual(len(mail.outbox), 0)

    def test_pendiente_se_rechaza_con_motivo(self):
        documento = _crear_documento()

        respuesta = self._accion('financiero-rechazar', documento.id)

        self.assertEqual(respuesta.status_code, 200)
        documento.refresh_from_db()
        self.assertEqual((documento.doc_aprobado, documento.motivo_rechazo), (Documento.RECHAZADO, 'Motivo de prueba'))

    def test_rechazar_sin_motivo_es_400(self):
        documento = _crear_documento()

        self.assertEqual(self._accion('financiero-rechazar', documento.id, motivo='').status_code, 400)

    def test_aprobado_y_rechazado_se_pueden_revocar(self):
        for estado in (Documento.APROBADO, Documento.RECHAZADO):
            documento = _crear_documento(estado=estado)

            respuesta = self._accion('financiero-revocar', documento.id)

            self.assertEqual(respuesta.status_code, 200, estado)
            documento.refresh_from_db()
            self.assertEqual(documento.doc_aprobado, Documento.REVOCADO)

    def test_transiciones_invalidas_son_400_y_no_cambian_el_documento(self):
        casos = (
            ('financiero-aprobar', Documento.APROBADO),
            ('financiero-aprobar', Documento.REVOCADO),
            ('financiero-aprobar', Documento.RECHAZADO),
            ('financiero-rechazar', Documento.APROBADO),
            ('financiero-rechazar', Documento.REVOCADO),
            ('financiero-revocar', Documento.PENDIENTE),
            ('financiero-revocar', Documento.REVOCADO),
        )
        for accion, estado in casos:
            documento = _crear_documento(estado=estado)

            respuesta = self._accion(accion, documento.id)

            self.assertEqual(respuesta.status_code, 400, f'{accion} desde {estado!r}')
            documento.refresh_from_db()
            self.assertEqual(documento.doc_aprobado, estado)

    def test_documento_inexistente_es_404(self):
        self.assertEqual(self._accion('financiero-aprobar', 99999).status_code, 404)

    def test_un_documento_sin_estado_se_trata_como_pendiente(self):
        documento = _crear_documento()
        Documento.objects.filter(pk=documento.pk).update(doc_aprobado=None)

        self.assertEqual(self._accion('financiero-aprobar', documento.id).status_code, 200)


class ResumenYCatalogosTests(ApiTestCase):
    def test_resumen_de_un_usuario_solo_cuenta_su_financiera(self):
        _crear_documento(financiera_id='001')
        _crear_documento(financiera_id='002')

        usuario = self.cliente_usuario.get(reverse('financiero-resumen')).data
        admin = self.cliente_admin.get(reverse('financiero-resumen')).data

        self.assertEqual(usuario['pendientes'], 1)
        self.assertEqual(admin['pendientes'], 2)
        self.assertEqual(set(usuario), {'pendientes', 'rechazados_mes', 'nuevos_semana'})

    def test_catalogos_mantienen_su_forma_y_las_notificaciones_son_por_usuario(self):
        _crear_documento(financiera_id='002')

        usuario = self.cliente_usuario.get(reverse('financiero-catalogos')).data
        admin = self.cliente_admin.get(reverse('financiero-catalogos')).data

        self.assertEqual(
            set(usuario),
            {'anios', 'meses', 'corporaciones', 'rango_vigente', 'notificaciones_pendientes', 'usuario_acceso'},
        )
        self.assertEqual((usuario['notificaciones_pendientes'], admin['notificaciones_pendientes']), (0, 1))
        self.assertEqual(usuario['usuario_acceso'], {'rol_id': 2, 'permisos': ['financiero.subir'], 'financiera_id': '001', 'financiera_ids': ['001']})
        self.assertEqual(len(usuario['corporaciones'][0]['financieras']), 2)

    def test_guardar_el_rango_invalida_la_cache_de_catalogos(self):
        self.assertIsNone(self.cliente_usuario.get(reverse('financiero-catalogos')).data['rango_vigente'])

        with self.captureOnCommitCallbacks(execute=True):
            self.cliente_admin.post(reverse('financiero-rango-fechas'), {'desde': '2026-10-01', 'hasta': '2026-10-31'}, format='json')

        rango = self.cliente_usuario.get(reverse('financiero-catalogos')).data['rango_vigente']
        self.assertEqual(str(rango['desde']), '2026-10-01')

    def test_catalogos_globales_se_consultan_una_sola_vez(self):
        self.cliente_usuario.get(reverse('financiero-catalogos'))

        # Segunda petición: solo lo que depende del usuario (autenticación forzada no consulta): sus entidades (dos veces,
        # una para el alcance de los pendientes y otra para mostrarlas) y el conteo de pendientes.
        with self.assertNumQueries(3):
            self.cliente_usuario.get(reverse('financiero-catalogos'))


class DatosDePruebaTests(ApiTestCase):
    def test_otro_usuario_de_la_misma_financiera_ve_los_mismos_documentos(self):
        _crear_documento()
        compañero = crear_usuario(rol_id=2, financiera_id='001')

        respuesta = cliente_de(compañero).get(reverse('financiero-documentos'), PARAMETROS)

        self.assertEqual(len(respuesta.data), 1)


PERIODO = {'anio': 2026, 'mes': 10, 'corporacion': '001'}


class PeriodoTests(ApiTestCase):
    def _filas(self, cliente) -> dict:
        datos = cliente.get(reverse('financiero-periodo'), PERIODO).data
        return {fila['financiera_id']: fila for fila in datos['financieras']}

    def test_el_admin_ve_todas_las_financieras_de_la_corporacion(self):
        respuesta = self.cliente_admin.get(reverse('financiero-periodo'), PERIODO)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual({f['financiera_id'] for f in respuesta.data['financieras']}, {'001', '002'})

    def test_un_usuario_solo_ve_su_financiera(self):
        self.assertEqual(set(self._filas(self.cliente_usuario)), {'001'})

    def test_una_financiera_sin_documento_figura_como_sin_cargar(self):
        filas = self._filas(self.cliente_admin)

        self.assertEqual(filas['001']['estado'], 'sin_cargar')
        self.assertIsNone(filas['001']['documento_id'])

    def test_cuenta_el_ultimo_documento_de_cada_financiera(self):
        _crear_documento(estado=Documento.RECHAZADO, financiera_id='001')
        ultimo = _crear_documento(estado=Documento.APROBADO, financiera_id='001')

        filas = self._filas(self.cliente_admin)

        self.assertEqual(filas['001']['estado'], 'aprobado')
        self.assertEqual(filas['001']['documento_id'], ultimo.id)

    def test_resumen_separa_cargadas_de_las_que_faltan(self):
        _crear_documento(estado=Documento.APROBADO, financiera_id='001')
        _crear_documento(estado=Documento.RECHAZADO, financiera_id='002')

        resumen = self.cliente_admin.get(reverse('financiero-periodo'), PERIODO).data['resumen']

        self.assertEqual((resumen['total'], resumen['cargadas'], resumen['faltan']), (2, 1, 1))
        self.assertEqual(resumen['por_estado']['aprobado'], 1)
        self.assertEqual(resumen['por_estado']['rechazado'], 1)

    def test_la_fila_muestra_el_motivo_del_rechazo(self):
        documento = _crear_documento(estado=Documento.RECHAZADO, financiera_id='001')
        documento.motivo_rechazo = 'Falta el balance'
        documento.save()

        self.assertEqual(self._filas(self.cliente_admin)['001']['motivo'], 'Falta el balance')

    def test_un_documento_con_estado_nulo_cuenta_como_pendiente(self):
        _crear_documento(estado=None, financiera_id='001')

        self.assertEqual(self._filas(self.cliente_admin)['001']['estado'], 'pendiente')

    def test_periodo_invalido_es_400(self):
        respuesta = self.cliente_admin.get(reverse('financiero-periodo'), {**PERIODO, 'corporacion': '999'})

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('corporacion', respuesta.data)


class HistorialTests(ApiTestCase):
    def test_lista_los_eventos_en_orden(self):
        ahora = timezone.now()
        documento = _crear_documento(estado=Documento.RECHAZADO)
        documento.fecha = ahora - timedelta(days=2)
        documento.fecha_rechaza = ahora - timedelta(days=1)
        documento.email_usuario_rechaza = 'admin@inversa.hn'
        documento.motivo_rechazo = 'Falta firma'
        documento.save()

        eventos = self.cliente_admin.get(reverse('financiero-historial', args=[documento.id])).data

        self.assertEqual([e['tipo'] for e in eventos], ['subido', 'rechazado'])
        self.assertEqual(eventos[0]['email'], 'sube@inversa.hn')
        self.assertEqual((eventos[1]['email'], eventos[1]['motivo']), ('admin@inversa.hn', 'Falta firma'))

    def test_la_revocacion_toma_el_autor_de_la_bitacora(self):
        documento = _crear_documento(estado=Documento.APROBADO)

        self.cliente_admin.post(reverse('financiero-revocar', args=[documento.id]), {'motivo': 'Error de periodo'}, format='json')
        eventos = self.cliente_admin.get(reverse('financiero-historial', args=[documento.id])).data

        revocado = [e for e in eventos if e['tipo'] == 'revocado'][0]
        self.assertEqual((revocado['email'], revocado['motivo']), ('admin@inversa.hn', 'Error de periodo'))

    def test_un_usuario_no_ve_el_historial_de_otra_financiera(self):
        documento = _crear_documento(financiera_id='002')

        self.assertEqual(self.cliente_usuario.get(reverse('financiero-historial', args=[documento.id])).status_code, 403)

    def test_documento_inexistente_es_404(self):
        self.assertEqual(self.cliente_admin.get(reverse('financiero-historial', args=[999])).status_code, 404)


class AniosDeLaVentanaTests(ApiTestCase):
    def _fijar(self, desde: str, hasta: str):
        return self.cliente_admin.post(reverse('financiero-rango-fechas'), {'desde': desde, 'hasta': hasta}, format='json')

    def test_abrir_una_ventana_en_un_anio_nuevo_lo_crea(self):
        self.assertFalse(Anio.objects.filter(id_anio=2027).exists())

        self.assertEqual(self._fijar('2027-01-10', '2027-01-20').status_code, 201)

        self.assertEqual(Anio.objects.get(id_anio=2027).anio, 2027)

    def test_una_ventana_entre_dos_anios_crea_ambos_sin_duplicar(self):
        self._fijar('2027-12-20', '2028-01-05')
        self._fijar('2027-12-21', '2028-01-06')

        self.assertEqual(Anio.objects.filter(id_anio__in=[2027, 2028]).count(), 2)

    def test_un_anio_existente_no_se_modifica(self):
        self._fijar('2026-10-01', '2026-10-31')

        self.assertEqual(Anio.objects.filter(id_anio=2026).count(), 1)
