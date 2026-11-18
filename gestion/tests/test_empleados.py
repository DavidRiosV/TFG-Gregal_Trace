"""Apartado Empleados: alta, edición y baja de oficiales y peones."""
from django.urls import reverse

from gestion.models import Usuario

from .base import PruebaBase


class Empleados(PruebaBase):
    DATOS = {'rol': Usuario.PEON, 'first_name': 'Xisco', 'last_name': 'Mas', 'username': 'xisco',
             'email': '', 'password1': 'Gregal-Prueba-26', 'password2': 'Gregal-Prueba-26', 'is_active': 'on'}

    def setUp(self):
        self.client.force_login(self.oficina)

    def test_dar_de_alta(self):
        self.client.post(reverse('empleado_crear'), self.DATOS)
        xisco = Usuario.objects.get(username='xisco')
        self.assertEqual(xisco.rol, Usuario.PEON)
        self.assertTrue(xisco.check_password('Gregal-Prueba-26'))
        self.assertTrue(xisco.groups.filter(name='Operarios').exists())

    def test_las_contrasenas_tienen_que_coincidir(self):
        respuesta = self.client.post(reverse('empleado_crear'), {**self.DATOS, 'password2': 'otra'})
        self.assertContains(respuesta, 'no coinciden')
        self.assertFalse(Usuario.objects.filter(username='xisco').exists())

    def test_no_se_puede_crear_oficina(self):
        self.client.post(reverse('empleado_crear'), {**self.DATOS, 'rol': Usuario.OFICINA})
        self.assertFalse(Usuario.objects.filter(username='xisco').exists())

    def test_editar_sin_cambiar_la_contrasena(self):
        self.client.post(reverse('empleado_editar', args=[self.peon.pk]), {
            **self.DATOS, 'username': 'toni', 'rol': Usuario.OFICIAL, 'password1': '', 'password2': '',
        })
        self.peon.refresh_from_db()
        self.assertEqual(self.peon.rol, Usuario.OFICIAL)
        self.assertTrue(self.peon.check_password(self.CLAVE))

    def test_oficina_no_se_edita_desde_aqui(self):
        self.assertEqual(self.client.get(reverse('empleado_editar', args=[self.oficina.pk])).status_code, 404)

    def test_borrar_sin_apuntes(self):
        self.client.post(reverse('empleado_eliminar', args=[self.peon.pk]))
        self.assertFalse(Usuario.objects.filter(pk=self.peon.pk).exists())
