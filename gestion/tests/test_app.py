"""App instalable (PWA): service worker, página «Sin conexión» y manifest."""
from django.test import TestCase
from django.urls import reverse

from .base import PruebaBase


class AppInstalable(TestCase):
    def test_service_worker_en_la_raiz(self):
        respuesta = self.client.get('/sw.js')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('javascript', respuesta['Content-Type'])
        # Solo guarda la página «Sin conexión»
        self.assertContains(respuesta, reverse('sin_conexion'))

    def test_sin_conexion_se_ve_sin_iniciar_sesion(self):
        respuesta = self.client.get(reverse('sin_conexion'))
        self.assertContains(respuesta, 'Sin conexión')


class EnlacesEnLasPaginas(PruebaBase):
    def test_manifest_y_registro(self):
        self.client.force_login(self.peon)
        respuesta = self.client.get(reverse('index'))
        self.assertContains(respuesta, 'pwa/manifest.webmanifest')
        self.assertContains(respuesta, 'apple-touch-icon')
