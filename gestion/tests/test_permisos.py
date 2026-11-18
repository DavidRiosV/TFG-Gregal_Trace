"""Quién puede entrar en cada página."""
from django.urls import reverse

from .base import PruebaBase


class AccesoSinSesion(PruebaBase):
    def test_sin_sesion_va_al_login(self):
        # Ninguna página de la aplicación se ve sin iniciar sesión
        for nombre in ['index', 'lista_citas', 'lista_materiales', 'lista_empleados']:
            respuesta = self.client.get(reverse(nombre))
            self.assertEqual(respuesta.status_code, 302, nombre)
            self.assertIn('/accounts/login/', respuesta.url)

    def test_el_login_se_ve(self):
        self.assertEqual(self.client.get('/accounts/login/').status_code, 200)


class PaginasDeOficina(PruebaBase):
    PAGINAS = ['lista_materiales', 'precios_horas', 'lista_empleados', 'empleados_oficina',
               'lista_citas', 'lista_albaranes', 'lista_categorias', 'lista_tipos']

    def test_oficina_entra(self):
        self.client.force_login(self.oficina)
        for nombre in self.PAGINAS:
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)

    def test_operarios_no_entran(self):
        # Un oficial o un peón vuelve al inicio de sesión (no tiene el permiso)
        for usuario in (self.oficial, self.peon):
            self.client.force_login(usuario)
            for nombre in self.PAGINAS:
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 302, f'{usuario} {nombre}')


class PaginasDeTodos(PruebaBase):
    def test_inicio_y_proyecto(self):
        for usuario in (self.oficina, self.oficial, self.peon):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('index')).status_code, 200)
            self.assertEqual(self.client.get(reverse('detalle_proyecto', args=[self.obra.pk])).status_code, 200)
            self.assertEqual(self.client.get(reverse('lista_proyectos', args=['obras'])).status_code, 200)
