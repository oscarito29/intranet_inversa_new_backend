"""Fábricas y utilidades compartidas por las pruebas de todas las apps."""

import hashlib
import itertools
from io import BytesIO

from django.core.cache import cache
from django.test import TestCase
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from rest_framework.test import APIClient

from apps.financial.models import Anio, Mes
from apps.usuarios.models import Corporacion, Financiera, Rol, Usuario

_contador = itertools.count(1)


def crear_catalogos() -> dict:
    """Los cuatro roles, una corporación con dos financieras, un año y un mes."""
    rol_admin, _ = Rol.objects.get_or_create(id=1, defaults={'name': 'Admin'})
    rol_usuario, _ = Rol.objects.get_or_create(id=2, defaults={'name': 'User'})
    Rol.objects.get_or_create(id=3, defaults={'name': 'Aprobador'})
    Rol.objects.get_or_create(id=4, defaults={'name': 'Consulta'})
    corporacion, _ = Corporacion.objects.get_or_create(id='001', defaults={'tipo_corporacion': 'FINANCIERAS'})
    otra_corporacion, _ = Corporacion.objects.get_or_create(id='002', defaults={'tipo_corporacion': 'OTROS'})
    fin_a, _ = Financiera.objects.get_or_create(id='001', defaults={'nombre': 'FINANCIERA A', 'corporacion': corporacion})
    fin_b, _ = Financiera.objects.get_or_create(id='002', defaults={'nombre': 'FINANCIERA B', 'corporacion': corporacion})
    fin_c, _ = Financiera.objects.get_or_create(id='003', defaults={'nombre': 'FINANCIERA C', 'corporacion': otra_corporacion})
    Anio.objects.get_or_create(id_anio=2026, defaults={'anio': 2026})
    Mes.objects.get_or_create(id_mes=10, defaults={'mes': 'Octubre'})
    return {'corporacion': corporacion, 'otra_corporacion': otra_corporacion, 'fin_a': fin_a, 'fin_b': fin_b, 'fin_c': fin_c}


def crear_usuario(rol_id: int = 2, financiera_id: str = '001', password: str = 'Clave-segura-123', **extra) -> Usuario:
    numero = next(_contador)
    usuario = Usuario(
        name=extra.pop('name', f'usuario{numero}'),
        email=extra.pop('email', f'usuario{numero}@inversa.hn'),
        full_name='Usuario de prueba',
        phone_number='99999999',
        address='Dirección',
        rol_id=rol_id,
        financiera_id=financiera_id,
        estado=extra.pop('estado', 'A'),
        **extra,
    )
    usuario.set_password(password)
    usuario.save()
    return usuario


def hoja_activa(contenido: bytes) -> Worksheet:
    """La hoja de un Excel descargado, para revisar lo que contiene."""
    hoja = load_workbook(BytesIO(contenido)).active
    assert isinstance(hoja, Worksheet), 'el libro no trae una hoja de cálculo'
    return hoja


def hash_md5_legado(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def cliente_de(usuario: Usuario | None) -> APIClient:
    cliente = APIClient()
    if usuario is not None:
        cliente.force_authenticate(user=usuario)
    return cliente


class ApiTestCase(TestCase):
    """Catálogos listos, caché limpia y dos usuarios de cada rol."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.catalogos = crear_catalogos()
        self.admin = crear_usuario(rol_id=1, financiera_id='001', email='admin@inversa.hn')
        self.usuario = crear_usuario(rol_id=2, financiera_id='001', email='usuario@inversa.hn')
        self.cliente_admin = cliente_de(self.admin)
        self.cliente_usuario = cliente_de(self.usuario)
