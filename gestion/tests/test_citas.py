"""Apartado Citas de Oficina."""
from datetime import date, timedelta

from django.urls import reverse

from gestion.models import Cita

from .base import PruebaBase


class Citas(PruebaBase):
    def setUp(self):
        self.client.force_login(self.oficina)

    def test_agendar_una_cita(self):
        respuesta = self.client.post(reverse('lista_citas'), {
            'proyecto': self.obra.pk, 'fecha': '2026-12-01', 'hora': '09:30', 'motivo': '  visita   de obra ',
        })
        self.assertEqual(respuesta.status_code, 302)
        cita = Cita.objects.get()
        self.assertEqual(cita.proyecto, self.obra)
        self.assertEqual(cita.motivo, 'Visita de obra')     # espacios fuera y mayúscula
        self.assertEqual(cita.creada_por, self.oficina)

    def test_no_se_agenda_en_un_trabajo_terminado(self):
        self.client.post(reverse('lista_citas'), {'proyecto': self.terminada.pk, 'fecha': '2026-12-01'})
        self.assertFalse(Cita.objects.exists())

    def test_hace_falta_trabajo_y_fecha(self):
        respuesta = self.client.post(reverse('lista_citas'), {'proyecto': '', 'fecha': ''})
        self.assertContains(respuesta, 'Elige a qué trabajo va la cita.')
        self.assertContains(respuesta, 'Elige el día de la cita.')

    def test_proximas_y_pasadas(self):
        Cita.objects.create(proyecto=self.obra, fecha=date.today() + timedelta(days=3), motivo='Futura')
        Cita.objects.create(proyecto=self.obra, fecha=date.today() - timedelta(days=3), motivo='Antigua')
        proximas = self.client.get(reverse('lista_citas'))
        self.assertContains(proximas, 'Futura')
        self.assertNotContains(proximas, 'Antigua')
        pasadas = self.client.get(reverse('lista_citas') + '?ver=pasadas')
        self.assertContains(pasadas, 'Antigua')

    def test_editar_y_cambiar_de_trabajo(self):
        otra = self.obra.__class__.objects.create(nombre='MAN26001 · Otra', tipo='MAN')
        cita = Cita.objects.create(proyecto=self.obra, fecha=date.today())
        self.client.post(reverse('cita_editar', args=[cita.pk]),
                         {'proyecto': otra.pk, 'fecha': '2026-12-02', 'hora': '', 'motivo': 'Revisión'})
        cita.refresh_from_db()
        self.assertEqual(cita.proyecto, otra)
        self.assertEqual(cita.motivo, 'Revisión')

    def test_borrar_vuelve_a_la_lista_pero_no_a_otra_web(self):
        cita = Cita.objects.create(proyecto=self.obra, fecha=date.today())
        respuesta = self.client.post(reverse('cita_eliminar', args=[cita.pk]), {'volver': '/citas/?ver=todas'})
        self.assertEqual(respuesta.url, '/citas/?ver=todas')
        cita = Cita.objects.create(proyecto=self.obra, fecha=date.today())
        respuesta = self.client.post(reverse('cita_eliminar', args=[cita.pk]), {'volver': 'https://otra-web.com/'})
        self.assertNotIn('otra-web', respuesta.url)
