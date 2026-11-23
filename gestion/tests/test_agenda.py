"""Agenda de empleados: Oficina asigna a cada oficial o peón un trabajo abierto por día y franja."""
from datetime import date, timedelta
from unittest import mock

from django.test import override_settings
from django.urls import reverse

from gestion.avisos import avisar_asignacion, texto_aviso
from gestion.models import Asignacion

from .base import PruebaBase


class Agenda(PruebaBase):
    def agendar(self, empleado=None, **datos):
        self.client.force_login(self.oficina)
        datos = {'fecha': '2026-12-01', 'franja': 'DIA', 'proyecto': self.obra.pk, 'nota': '', **datos}
        return self.client.post(reverse('empleado_agenda', args=[(empleado or self.peon).pk]), datos)

    def test_oficina_agenda_un_trabajo(self):
        respuesta = self.agendar(nota='  llevar   la escalera ')
        self.assertEqual(respuesta.status_code, 302)
        asignacion = Asignacion.objects.get()
        self.assertEqual(asignacion.empleado, self.peon)
        self.assertEqual(asignacion.creada_por, self.oficina)
        self.assertEqual(asignacion.nota, 'Llevar la escalera')
        # Vuelve a la semana del día agendado (el 1/12/2026 es martes: la semana empieza el lunes 30/11)
        self.assertIn('semana=2026-11-30', respuesta.url)

    def test_solo_trabajos_abiertos(self):
        self.agendar(proyecto=self.terminada.pk)
        self.assertFalse(Asignacion.objects.exists())

    def test_manana_y_tarde_si_pero_no_dos_veces_lo_mismo(self):
        self.agendar(franja='MAN')
        self.agendar(franja='TAR')
        self.assertEqual(Asignacion.objects.count(), 2)
        respuesta = self.agendar(franja='MAN')
        self.assertContains(respuesta, 'Ese día ya tiene trabajo a esa hora.')
        self.agendar(franja='DIA')
        self.assertEqual(Asignacion.objects.count(), 2)

    def test_solo_a_oficiales_y_peones(self):
        self.client.force_login(self.oficina)
        self.assertEqual(self.client.get(reverse('empleado_agenda', args=[self.oficina.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('empleado_agenda', args=[self.oficial.pk])).status_code, 200)

    def test_los_operarios_no_agendan(self):
        self.client.force_login(self.oficial)
        self.client.post(reverse('empleado_agenda', args=[self.peon.pk]),
                         {'fecha': '2026-12-01', 'franja': 'DIA', 'proyecto': self.obra.pk})
        self.assertFalse(Asignacion.objects.exists())

    def test_quitar(self):
        self.agendar()
        asignacion = Asignacion.objects.get()
        self.client.post(reverse('asignacion_eliminar', args=[asignacion.pk]))
        self.assertFalse(Asignacion.objects.exists())

    def test_el_empleado_lo_ve_en_su_inicio(self):
        Asignacion.objects.create(empleado=self.peon, proyecto=self.obra, fecha=date.today(), franja='MAN')
        Asignacion.objects.create(empleado=self.oficial, proyecto=self.obra, fecha=date.today() + timedelta(days=1))
        self.client.force_login(self.peon)
        respuesta = self.client.get(reverse('index'))
        self.assertContains(respuesta, 'Mi semana')
        self.assertContains(respuesta, 'Hoy · mañana')
        self.assertEqual(len(respuesta.context['mi_semana']), 1)   # solo lo suyo


class AvisoWhatsApp(PruebaBase):
    def setUp(self):
        self.peon.telefono = '600111222'
        self.peon.save()
        self.asignacion = Asignacion.objects.create(empleado=self.peon, proyecto=self.obra, fecha=date(2026, 12, 3), franja='TAR')

    def test_texto_del_mensaje(self):
        self.assertEqual(texto_aviso(self.asignacion), 'Hola Toni, el 03/12 (tarde) vas a OBR26001 · Prueba · Marta Pons.')

    def test_sin_configurar_no_se_envia(self):
        self.assertFalse(avisar_asignacion(self.asignacion))
        self.assertIsNone(self.asignacion.avisada)

    @override_settings(WHATSAPP_WEBHOOK_URL='https://n8n.ejemplo/webhook/aviso')
    def test_configurado_se_envia_al_webhook(self):
        # urlopen se sustituye por uno falso: la prueba no sale a internet
        with mock.patch('gestion.avisos.urllib.request.urlopen') as urlopen:
            self.assertTrue(avisar_asignacion(self.asignacion))
        peticion = urlopen.call_args.args[0]
        self.assertEqual(peticion.full_url, 'https://n8n.ejemplo/webhook/aviso')
        self.assertIn(b'600111222', peticion.data)
        self.assertIsNotNone(self.asignacion.avisada)

    @override_settings(WHATSAPP_WEBHOOK_URL='https://n8n.ejemplo/webhook/aviso')
    def test_si_falla_el_envio_la_agenda_sigue(self):
        with mock.patch('gestion.avisos.urllib.request.urlopen', side_effect=OSError):
            self.assertFalse(avisar_asignacion(self.asignacion))


class CalendarioTrabajadores(PruebaBase):
    def setUp(self):
        self.client.force_login(self.oficina)
        Asignacion.objects.create(empleado=self.peon, proyecto=self.obra, fecha=date.today(), franja='MAN', nota='Con la furgoneta')

    def test_se_ve_quien_va_adonde(self):
        respuesta = self.client.get(reverse('calendario') + '?ver=trabajadores')
        self.assertContains(respuesta, 'Toni')
        self.assertContains(respuesta, self.obra.nombre)
        self.assertContains(respuesta, 'Con la furgoneta')
        # Pablo (oficial) no tiene nada hoy: sale en «Sin agendar»
        hoy = next(d for d in respuesta.context['dias'] if d['es_hoy'])
        self.assertEqual([e.username for e in hoy['sin_agendar']], ['pablo'])

    def test_no_mezcla_con_citas(self):
        respuesta = self.client.get(reverse('calendario') + '?ver=citas')
        self.assertNotContains(respuesta, 'Con la furgoneta')
