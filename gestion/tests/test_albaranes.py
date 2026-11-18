"""Subir albaranes y fotos de la obra."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from gestion.models import Albaran

from .base import PruebaBase


class Albaranes(PruebaBase):
    def subir(self, nombre, contenido, tipo='ALB'):
        self.client.force_login(self.oficial)
        return self.client.post(reverse('detalle_proyecto', args=[self.obra.pk]), {
            'apunte': 'albaran', 'tipo': tipo, 'descripcion': nombre,
            'archivo': SimpleUploadedFile(nombre, contenido),
        })

    def test_pdf_y_foto(self):
        self.subir('albaran.pdf', b'%PDF-1.4 prueba')
        self.subir('obra.jpg', b'\xff\xd8\xff' + b'0' * 20, tipo='FOT')
        self.assertEqual(Albaran.objects.count(), 2)
        self.assertEqual(Albaran.objects.get(tipo='FOT').etiqueta(), 'FOTO')

    def test_no_vale_cambiar_la_extension(self):
        self.subir('falso.pdf', b'esto no es un pdf')
        self.subir('falso.jpg', b'tampoco una foto')
        self.subir('programa.exe', b'MZ')
        self.assertFalse(Albaran.objects.exists())

    def test_solo_se_ve_con_sesion(self):
        self.subir('albaran.pdf', b'%PDF-1.4 prueba')
        albaran = Albaran.objects.get()
        self.assertEqual(self.client.get(reverse('albaran_ver', args=[albaran.pk])).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('albaran_ver', args=[albaran.pk])).status_code, 302)
