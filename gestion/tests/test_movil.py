"""Barra inferior del móvil: Oficina tiene los grupos de la web; oficiales y peones, accesos directos."""
from django.urls import reverse

from .base import PruebaBase


class BarraMovil(PruebaBase):
    def barra(self, usuario):
        self.client.force_login(usuario)
        html = self.client.get(reverse('index')).content.decode()
        return html[html.index('<nav class="pestanas'):]

    def test_oficina_tiene_grupos(self):
        barra = self.barra(self.oficina)
        for grupo in ('Trabajos', 'Gestión', 'Herramientas'):
            self.assertIn(f'<span>{grupo}</span>', barra)
        self.assertIn(reverse('lista_empleados'), barra)

    def test_operarios_tienen_accesos_directos(self):
        for usuario in (self.oficial, self.peon):
            barra = self.barra(usuario)
            self.assertNotIn('pestana-grupo', barra)
            for texto in ('Inicio', 'Obras', 'Mantenimientos', 'Urgencias'):
                self.assertIn(f'<span>{texto}</span>', barra)
            self.assertNotIn(reverse('lista_empleados'), barra)
