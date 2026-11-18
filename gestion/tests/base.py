"""Datos de partida que comparten todas las pruebas: un usuario de cada rol y un par de trabajos."""
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from gestion.models import CampoHora, Categoria, Material, Proyecto, Usuario

# Los archivos que se suben en las pruebas (albaranes, copia de las citas) van a una carpeta temporal,
# no a la carpeta media/ de verdad
CARPETA_MEDIA = tempfile.mkdtemp(prefix='gregal_pruebas_')


@override_settings(MEDIA_ROOT=CARPETA_MEDIA)
class PruebaBase(TestCase):
    # Los grupos «Oficina» y «Operarios» con sus permisos, como en la aplicación de verdad
    fixtures = ['grupos']
    CLAVE = 'Clave-de-prueba-2026'

    @classmethod
    def setUpTestData(cls):
        # setUpTestData se ejecuta una sola vez para toda la clase (más rápido que setUp)
        cls.oficina = cls.crear_usuario('marta', Usuario.OFICINA, 'Oficina')
        cls.oficial = cls.crear_usuario('pablo', Usuario.OFICIAL, 'Operarios')
        cls.peon = cls.crear_usuario('toni', Usuario.PEON, 'Operarios')
        cls.obra = Proyecto.objects.create(nombre='OBR26001 · Prueba', tipo='OBR', cliente='Marta Pons')
        cls.terminada = Proyecto.objects.create(nombre='OBR26002 · Terminada', tipo='OBR', estado='TER',
                                                fecha_fin=date.today())
        # Las horas son materiales de la familia «Mano de obra»; los campos (Electricidad...) los crea una migración
        mano_de_obra, _ = Categoria.objects.get_or_create(codigo='MOB', defaults={'nombre': 'Mano de obra y servicios'})
        cls.hora_oficial, _ = Material.objects.get_or_create(
            nombre='Hora Oficial', defaults={'categoria': mano_de_obra, 'unidad': 'H', 'precio': Decimal('32.00'), 'clase': ''})
        cls.hora_peon, _ = Material.objects.get_or_create(
            nombre='Hora Peón', defaults={'categoria': mano_de_obra, 'unidad': 'H', 'precio': Decimal('25.00'), 'clase': ''})
        cls.electricidad = CampoHora.objects.get(nombre='Electricidad')
        # Un material normal (no horas), para las pruebas de material
        cls.tuberia = Material.objects.create(nombre='Tubería PPR 25 mm', categoria=mano_de_obra, unidad='M',
                                              precio=Decimal('3.40'))

    @classmethod
    def crear_usuario(cls, nombre, rol, grupo):
        usuario = Usuario.objects.create_user(nombre, password=cls.CLAVE, first_name=nombre.title(), rol=rol)
        Group.objects.get(name=grupo).user_set.add(usuario)
        return usuario

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(CARPETA_MEDIA, ignore_errors=True)
