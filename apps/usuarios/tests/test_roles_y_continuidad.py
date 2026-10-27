"""Gestión de roles y entidades de una persona, y las reglas que impiden dejar al sistema sin quien administre o apruebe."""

from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.testing import ApiTestCase, cliente_de, crear_usuario
from apps.financial.models import Bitacora
from apps.usuarios.models import Rol, Usuario, UsuarioEntidad
from apps.usuarios.tests.test_gestion import _payload


def _editar(cliente, usuario, **datos):
    return cliente.patch(reverse('usuarios-detail', args=[usuario.pk]), datos, format='json')


class RolesNuevosTests(ApiTestCase):
    def test_se_puede_crear_una_persona_con_cada_rol_conocido(self):
        for rol in (1, 2, 3, 4):
            with self.subTest(rol=rol):
                respuesta = self.cliente_admin.post(reverse('usuarios-list-create'), _payload(email=f'rol{rol}@inversa.hn', rol_id=rol), format='json')
                self.assertEqual(respuesta.status_code, 201, respuesta.data)

    def test_el_rol_5_no_se_puede_asignar_aunque_exista_en_la_tabla(self):
        Rol.objects.create(id=5, name='Reservado')  # lo que haría alguien que agregue un rol a la base sin pasar por el sistema

        respuesta = self.cliente_admin.post(reverse('usuarios-list-create'), _payload(rol_id=5), format='json')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('rol_id', respuesta.data)

    def test_un_rol_que_no_existe_es_400(self):
        self.assertEqual(self.cliente_admin.post(reverse('usuarios-list-create'), _payload(rol_id=99), format='json').status_code, 400)

    def test_un_rol_sin_permisos_definidos_no_puede_nada(self):
        from apps.core.permissions import permisos_del_rol

        self.assertEqual(permisos_del_rol(5), frozenset())
        self.assertEqual(permisos_del_rol(None), frozenset())

    def test_me_trae_los_permisos_y_las_entidades_de_la_persona(self):
        UsuarioEntidad.objects.create(usuario=self.usuario, financiera_id='003')

        datos = self.cliente_usuario.get(reverse('me')).data

        self.assertEqual(datos['permisos'], ['financiero.subir'])
        self.assertEqual(datos['financiera_ids'], ['001', '003'])

    def test_cada_rol_recibe_los_permisos_de_su_tabla(self):
        esperados = {
            1: 10,  # el administrador tiene todos los permisos
            3: 3,
            4: 2,
            2: 1,
        }
        for rol, cantidad in esperados.items():
            with self.subTest(rol=rol):
                persona = crear_usuario(rol_id=rol, email=f'p{rol}@inversa.hn')
                self.assertEqual(len(cliente_de(persona).get(reverse('me')).data['permisos']), cantidad)


class CorreoPropioTests(ApiTestCase):
    def test_solo_quien_administra_usuarios_cambia_su_correo(self):
        for rol, puede in ((1, True), (2, False), (3, False), (4, False)):
            with self.subTest(rol=rol):
                persona = crear_usuario(rol_id=rol, email=f'yo{rol}@inversa.hn')
                cliente = cliente_de(persona)

                perfil = cliente.get(reverse('perfil')).data
                respuesta = cliente.patch(reverse('perfil'), {'name': 'Nombre', 'phone_number': '99999999', 'email': f'nuevo{rol}@inversa.hn'}, format='json')

                self.assertEqual(perfil['puede_editar_email'], puede)
                self.assertEqual(respuesta.status_code, 200 if puede else 400)


class EntidadesAdicionalesTests(ApiTestCase):
    def test_crear_con_entidades_adicionales(self):
        respuesta = self.cliente_admin.post(reverse('usuarios-list-create'), _payload(entidades_adicionales=['002', '003']), format='json')

        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data['entidades_adicionales'], ['002', '003'])
        self.assertEqual(Bitacora.objects.filter(descripcion__contains='Cambio de entidades adicionales de nuevo@inversa.hn: ninguna a 002, 003').count(), 1)

    def test_la_lista_y_el_detalle_traen_las_entidades_adicionales(self):
        UsuarioEntidad.objects.create(usuario=self.usuario, financiera_id='002')

        lista = {fila['email']: fila for fila in self.cliente_admin.get(reverse('usuarios-list-create')).data}
        detalle = self.cliente_admin.get(reverse('usuarios-detail', args=[self.usuario.pk])).data

        self.assertEqual(lista[self.usuario.email]['entidades_adicionales'], ['002'])
        self.assertEqual(lista[self.admin.email]['entidades_adicionales'], [])
        self.assertEqual(detalle['entidades_adicionales'], ['002'])

    def test_la_lista_no_hace_una_consulta_por_persona(self):
        for numero in range(10):
            persona = crear_usuario(email=f'masa{numero}@inversa.hn')
            UsuarioEntidad.objects.create(usuario=persona, financiera_id='002')
        with self.assertNumQueries(2):  # las personas y sus entidades adicionales
            self.cliente_admin.get(reverse('usuarios-list-create'))

    def test_editar_reemplaza_las_entidades_adicionales_y_queda_en_la_bitacora(self):
        UsuarioEntidad.objects.create(usuario=self.usuario, financiera_id='002')

        respuesta = _editar(self.cliente_admin, self.usuario, entidades_adicionales=['003'])

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data['entidades_adicionales'], ['003'])
        self.assertTrue(Bitacora.objects.filter(descripcion=f'Cambio de entidades adicionales de {self.usuario.email}: 002 a 003').exists())

    def test_una_lista_vacia_las_quita_todas_y_omitirla_no_las_toca(self):
        UsuarioEntidad.objects.create(usuario=self.usuario, financiera_id='002')

        _editar(self.cliente_admin, self.usuario, name='Otro nombre')
        self.assertEqual(UsuarioEntidad.objects.filter(usuario=self.usuario).count(), 1)

        _editar(self.cliente_admin, self.usuario, entidades_adicionales=[])
        self.assertEqual(UsuarioEntidad.objects.filter(usuario=self.usuario).count(), 0)

    def test_la_entidad_principal_no_se_repite_como_adicional_ni_hay_duplicados(self):
        respuesta = _editar(self.cliente_admin, self.usuario, entidades_adicionales=['001', '002', '002'])

        self.assertEqual(respuesta.data['entidades_adicionales'], ['002'])

    def test_una_entidad_que_no_existe_es_400_y_no_cambia_nada(self):
        respuesta = _editar(self.cliente_admin, self.usuario, entidades_adicionales=['002', '999'])

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('entidades_adicionales', respuesta.data)
        self.assertFalse(UsuarioEntidad.objects.filter(usuario=self.usuario).exists())

    def test_cambiar_la_entidad_principal_a_una_adicional_la_saca_de_las_adicionales(self):
        UsuarioEntidad.objects.create(usuario=self.usuario, financiera_id='002')

        respuesta = _editar(self.cliente_admin, self.usuario, userFinancieraId='002', entidades_adicionales=['002', '003'])

        self.assertEqual(respuesta.data['entidades_adicionales'], ['003'])

    def test_solo_el_administrador_las_gestiona(self):
        self.assertEqual(_editar(self.cliente_usuario, self.usuario, entidades_adicionales=['002']).status_code, 403)


class ContinuidadTests(ApiTestCase):
    """Con `ApiTestCase` hay un administrador; los demás se agregan en cada prueba."""

    def test_no_se_puede_dejar_menos_de_dos_personas_que_aprueben(self):
        otro_admin = crear_usuario(rol_id=1, email='otro.admin@inversa.hn')  # ahora son dos

        respuesta = _editar(self.cliente_admin, otro_admin, estado='I')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('al menos 2 personas', str(respuesta.data))
        otro_admin.refresh_from_db()
        self.assertEqual(otro_admin.estado, 'A')

    def test_degradar_a_un_aprobador_tambien_cuenta(self):
        aprobador = crear_usuario(rol_id=3, email='aprobador@inversa.hn')  # admin + aprobador = dos

        self.assertEqual(_editar(self.cliente_admin, aprobador, rol_id=2).status_code, 400)
        self.assertEqual(_editar(self.cliente_admin, aprobador, rol_id=4).status_code, 400)

    def test_con_tres_se_puede_quitar_uno(self):
        crear_usuario(rol_id=3, email='aprobador@inversa.hn')
        otro = crear_usuario(rol_id=1, email='otro.admin@inversa.hn')

        self.assertEqual(_editar(self.cliente_admin, otro, estado='I').status_code, 200)

    def test_lo_que_no_toca_a_los_aprobadores_no_se_bloquea(self):
        # Hoy hay un solo administrador (menos de dos); editar a un usuario normal no empeora nada.
        self.assertEqual(_editar(self.cliente_admin, self.usuario, estado='I').status_code, 200)

    def test_agregar_un_aprobador_nunca_se_bloquea(self):
        self.assertEqual(_editar(self.cliente_admin, self.usuario, rol_id=3).status_code, 200)

    def test_siempre_queda_un_administrador_activo(self):
        # Con muchos aprobadores la regla de los dos no estorba; la de un administrador sí.
        for numero in range(3):
            crear_usuario(rol_id=3, email=f'aprobador{numero}@inversa.hn')
        otro = crear_usuario(rol_id=1, email='otro.admin@inversa.hn')
        # el administrador de siempre se queda sin cuenta a manos del otro:
        respuesta = _editar(cliente_de(otro), self.admin, estado='I')
        self.assertEqual(respuesta.status_code, 200)  # quedan 'otro' y los aprobadores: sigue habiendo un administrador

        respuesta = _editar(cliente_de(otro), otro, estado='I')
        self.assertEqual(respuesta.status_code, 400)  # no puede desactivarse a sí mismo (regla anterior)
        self.assertEqual(Usuario.objects.filter(estado='A', rol_id=1).count(), 1)


class CierreDeSesionesTests(ApiTestCase):
    def _sesion_abierta(self, usuario) -> RefreshToken:
        return RefreshToken.for_user(usuario)

    def _cerradas(self, usuario) -> int:
        return BlacklistedToken.objects.filter(token__user_id=usuario.pk).count()

    def test_cambiar_el_rol_cierra_las_sesiones_de_esa_persona_y_no_las_de_otras(self):
        propia = self._sesion_abierta(self.usuario)
        ajena = self._sesion_abierta(self.admin)

        _editar(self.cliente_admin, self.usuario, rol_id=4)

        self.assertEqual((self._cerradas(self.usuario), self._cerradas(self.admin)), (1, 0))
        self.assertTrue(OutstandingToken.objects.filter(jti=propia['jti']).exists())
        self.assertFalse(BlacklistedToken.objects.filter(token__jti=ajena['jti']).exists())

    def test_cambiar_la_entidad_las_entidades_o_el_estado_tambien_las_cierra(self):
        cambios = (
            {'userFinancieraId': '002'},
            {'entidades_adicionales': ['003']},
            {'estado': 'I'},
        )
        for cambio in cambios:
            with self.subTest(cambio=cambio):
                persona = crear_usuario(email=f'p{len(str(cambio))}{list(cambio)[0]}@inversa.hn')
                self._sesion_abierta(persona)

                _editar(self.cliente_admin, persona, **cambio)

                self.assertEqual(self._cerradas(persona), 1)

    def test_editar_solo_el_nombre_no_cierra_nada(self):
        self._sesion_abierta(self.usuario)

        _editar(self.cliente_admin, self.usuario, name='Otro nombre')

        self.assertEqual(self._cerradas(self.usuario), 0)

    def test_con_la_sesion_cerrada_el_refresh_ya_no_sirve(self):
        sesion = self._sesion_abierta(self.usuario)
        cliente = APIClient()
        cliente.cookies[settings.REFRESH_TOKEN_COOKIE_NAME] = str(sesion)
        self.assertEqual(cliente.post(reverse('token_refresh')).status_code, 200)  # antes de cambiarle el rol, renueva

        nueva = RefreshToken.for_user(self.usuario)
        cliente.cookies[settings.REFRESH_TOKEN_COOKIE_NAME] = str(nueva)
        _editar(self.cliente_admin, self.usuario, rol_id=4)

        self.assertEqual(cliente.post(reverse('token_refresh')).status_code, 400)

    def test_el_cambio_de_rol_se_aplica_al_instante_aunque_su_token_siga_vigente(self):
        self.assertEqual(self.cliente_usuario.get(reverse('usuarios-roles')).status_code, 200)
        _editar(self.cliente_admin, self.usuario, rol_id=4)
        self.usuario.refresh_from_db()

        # El token de acceso no guarda el rol: el servidor lo lee de la base en cada petición.
        self.assertEqual(cliente_de(self.usuario).get(reverse('me')).data['permisos'], ['financiero.exportar', 'financiero.ver_todas'])
