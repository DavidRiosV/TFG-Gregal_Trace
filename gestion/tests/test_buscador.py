"""Buscador global (Ctrl+K)."""
from django.urls import reverse

from .base import PruebaBase


class Buscador(PruebaBase):
    def buscar(self, usuario, texto):
        self.client.force_login(usuario)
        return self.client.get(reverse('buscar'), {'q': texto}).json()['resultados']

    def test_encuentra_por_cliente(self):
        resultados = self.buscar(self.oficial, 'pons')
        self.assertEqual([r['titulo'] for r in resultados], [self.obra.nombre])

    def test_hacen_falta_dos_letras(self):
        self.assertEqual(self.buscar(self.oficina, 'o'), [])

    def test_el_operario_no_ve_empleados(self):
        grupos = {r['grupo'] for r in self.buscar(self.oficial, 'to')}
        self.assertNotIn('Empleados', grupos)
        grupos = {r['grupo'] for r in self.buscar(self.oficina, 'to')}
        self.assertIn('Empleados', grupos)
