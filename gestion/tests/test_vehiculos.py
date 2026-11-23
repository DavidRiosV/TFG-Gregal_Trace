"""Vehículos: alta (Oficina), kilometraje con registro de quién y cuándo, revisiones y anotaciones."""
from datetime import date, timedelta

from django.urls import reverse

from gestion.models import Kilometraje, NotaVehiculo, RevisionVehiculo, Vehiculo
from gestion.views.vehiculos import km_por_meses

from .base import PruebaBase


class Vehiculos(PruebaBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # La furgoneta la lleva Toni (peón)
        cls.furgoneta = Vehiculo.objects.create(tipo='FUR', matricula='1234 ABC', modelo='Toyota Proace', responsable=cls.peon)

    def url(self):
        return reverse('detalle_vehiculo', args=[self.furgoneta.pk])

    def test_oficina_da_de_alta(self):
        self.client.force_login(self.oficina)
        self.client.post(reverse('vehiculo_crear'), {'tipo': 'COC', 'matricula': ' 9876  xyz ', 'modelo': 'Peugeot Partner',
                                                      'responsable': self.oficial.pk, 'activo': 'on'})
        coche = Vehiculo.objects.get(matricula='9876 XYZ')
        self.assertEqual(coche.responsable, self.oficial)

    def test_el_responsable_lo_ve_y_los_demas_no(self):
        self.client.force_login(self.peon)
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        # Con un solo vehículo, «Vehículos» le lleva directo a él
        self.assertRedirects(self.client.get(reverse('lista_vehiculos')), self.url())
        self.client.force_login(self.oficial)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_apuntar_km_guarda_quien_y_cuando(self):
        self.client.force_login(self.peon)
        self.client.post(self.url(), {'apunte': 'km', 'fecha': '2026-11-20', 'km': '125430'})
        lectura = Kilometraje.objects.get()
        self.assertEqual(lectura.km, 125430)
        self.assertEqual(lectura.registrado_por, self.peon)
        self.assertIsNotNone(lectura.registrado)

    def test_el_cuentakilometros_no_va_hacia_atras(self):
        Kilometraje.objects.create(vehiculo=self.furgoneta, fecha=date(2026, 11, 1), km=120000, registrado_por=self.peon)
        self.client.force_login(self.peon)
        respuesta = self.client.post(self.url(), {'apunte': 'km', 'fecha': '2026-11-20', 'km': '119000'})
        self.assertContains(respuesta, 'no puede tener menos')
        self.assertEqual(Kilometraje.objects.count(), 1)

    def test_el_responsable_no_pone_revisiones_ni_edita(self):
        self.client.force_login(self.peon)
        self.client.post(self.url(), {'apunte': 'revision', 'tipo': 'ITV', 'fecha': '2026-12-10'})
        self.assertFalse(RevisionVehiculo.objects.exists())
        self.assertEqual(self.client.get(reverse('vehiculo_editar', args=[self.furgoneta.pk])).status_code, 302)

    def test_revision_en_el_calendario(self):
        self.client.force_login(self.oficina)
        self.client.post(self.url(), {'apunte': 'revision', 'tipo': 'ITV', 'fecha': date.today().isoformat(),
                                      'hora': '09:00', 'motivo': 'ITV Son Castelló'})
        self.assertEqual(RevisionVehiculo.objects.get().tipo, 'ITV')
        self.assertContains(self.client.get(reverse('calendario') + '?ver=vehiculos'), 'ITV Son Castelló')
        self.assertNotContains(self.client.get(reverse('calendario') + '?ver=citas'), 'ITV Son Castelló')
        # El responsable la ve en su vehículo
        self.client.force_login(self.peon)
        self.assertContains(self.client.get(self.url()), 'ITV Son Castelló')

    def test_anotaciones(self):
        self.client.force_login(self.peon)
        self.client.post(self.url(), {'apunte': 'nota', 'texto': 'Ruido en la rueda delantera'})
        nota = NotaVehiculo.objects.get()
        self.assertEqual(nota.autor, self.peon)
        # Oficina la ve; el responsable puede borrar la suya
        otra = NotaVehiculo.objects.create(vehiculo=self.furgoneta, autor=self.oficina, texto='Cambiar ruedas')
        self.client.post(reverse('nota_vehiculo_eliminar', args=[otra.pk]))
        self.assertTrue(NotaVehiculo.objects.filter(pk=otra.pk).exists())     # la de Oficina, no
        self.client.post(reverse('nota_vehiculo_eliminar', args=[nota.pk]))
        self.assertFalse(NotaVehiculo.objects.filter(pk=nota.pk).exists())

    def test_mi_vehiculo_en_el_inicio(self):
        self.client.force_login(self.peon)
        respuesta = self.client.get(reverse('index'))
        self.assertContains(respuesta, 'Mi vehículo')
        self.assertContains(respuesta, '1234 ABC')

    def test_km_por_meses(self):
        hoy = date.today().replace(day=15)
        mes_pasado = (hoy.replace(day=1) - timedelta(days=1)).replace(day=10)
        for fecha, km in [(mes_pasado, 1000), (hoy.replace(day=2), 1300), (hoy, 1750)]:
            Kilometraje.objects.create(vehiculo=self.furgoneta, fecha=fecha, km=km, registrado_por=self.peon)
        meses = km_por_meses(list(self.furgoneta.kilometrajes.all()))
        self.assertEqual(meses[0]['km'], 750)      # este mes: 1750 − 1000 (la última del mes pasado)
        # El mes pasado solo hay una lectura y ninguna antes: no se sabe (no son 0 km)
        self.assertIsNone(meses[1]['km'])
        self.assertTrue(meses[1]['primera'])

    def test_primera_lectura_del_vehiculo(self):
        # Una sola lectura en el mes: «—», no 0 km; con la segunda ya se calcula
        Kilometraje.objects.create(vehiculo=self.furgoneta, fecha=date.today().replace(day=1), km=5000, registrado_por=self.peon)
        self.assertIsNone(km_por_meses(list(self.furgoneta.kilometrajes.all()))[0]['km'])
        Kilometraje.objects.create(vehiculo=self.furgoneta, fecha=date.today(), km=5400, registrado_por=self.peon)
        self.assertEqual(km_por_meses(list(self.furgoneta.kilometrajes.all()))[0]['km'], 400)


class GestionDesdeOficina(PruebaBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.furgoneta = Vehiculo.objects.create(tipo='FUR', matricula='1234 ABC', modelo='Toyota Proace', responsable=cls.peon)

    def setUp(self):
        self.client.force_login(self.oficina)

    def editar(self, responsable):
        return self.client.post(reverse('vehiculo_editar', args=[self.furgoneta.pk]), {
            'tipo': 'FUR', 'matricula': '1234 ABC', 'modelo': 'Toyota Proace', 'responsable': responsable or '', 'activo': 'on'})

    def test_cambiar_de_responsable_deja_historial_y_respeta_lo_anterior(self):
        nota = NotaVehiculo.objects.create(vehiculo=self.furgoneta, autor=self.peon, texto='Ruido al frenar')
        lectura = Kilometraje.objects.create(vehiculo=self.furgoneta, fecha=date(2026, 11, 1), km=1000, registrado_por=self.peon)
        self.editar(self.oficial.pk)
        self.furgoneta.refresh_from_db()
        self.assertEqual(self.furgoneta.responsable, self.oficial)
        historial = NotaVehiculo.objects.get(automatica=True)
        self.assertIn('Toni', historial.texto)
        self.assertIn('Pablo', historial.texto)
        # Lo de antes sigue igual, con su autor
        nota.refresh_from_db()
        lectura.refresh_from_db()
        self.assertEqual((nota.autor, nota.texto), (self.peon, 'Ruido al frenar'))
        self.assertEqual(lectura.registrado_por, self.peon)
        # El anterior responsable ya no lo ve; el nuevo, sí
        self.client.force_login(self.peon)
        self.assertEqual(self.client.get(reverse('detalle_vehiculo', args=[self.furgoneta.pk])).status_code, 404)
        self.client.force_login(self.oficial)
        self.assertEqual(self.client.get(reverse('detalle_vehiculo', args=[self.furgoneta.pk])).status_code, 200)

    def test_sin_cambio_de_responsable_no_hay_historial(self):
        self.editar(self.peon.pk)
        self.assertFalse(NotaVehiculo.objects.filter(automatica=True).exists())

    def test_las_anotaciones_pasadas_no_se_borran(self):
        de_toni = NotaVehiculo.objects.create(vehiculo=self.furgoneta, autor=self.peon, texto='Rueda pinchada')
        historial = NotaVehiculo.objects.create(vehiculo=self.furgoneta, autor=self.oficina, texto='Cambio', automatica=True)
        self.client.post(reverse('nota_vehiculo_eliminar', args=[de_toni.pk]))
        self.client.post(reverse('nota_vehiculo_eliminar', args=[historial.pk]))
        self.assertEqual(NotaVehiculo.objects.count(), 2)

    def test_corregir_una_lectura_mantiene_quien_la_apunto(self):
        Kilometraje.objects.create(vehiculo=self.furgoneta, fecha=date(2026, 10, 1), km=900, registrado_por=self.peon)
        lectura = Kilometraje.objects.create(vehiculo=self.furgoneta, fecha=date(2026, 11, 1), km=1000, registrado_por=self.peon)
        self.client.post(reverse('kilometraje_editar', args=[lectura.pk]), {'fecha': '2026-11-01', 'km': '1050'})
        lectura.refresh_from_db()
        self.assertEqual(lectura.km, 1050)
        self.assertEqual(lectura.registrado_por, self.peon)
        # Tampoco deja poner menos que la anterior
        respuesta = self.client.post(reverse('kilometraje_editar', args=[lectura.pk]), {'fecha': '2026-11-01', 'km': '800'})
        self.assertContains(respuesta, 'no puede tener menos')

    def test_cambiar_una_revision(self):
        revision = RevisionVehiculo.objects.create(vehiculo=self.furgoneta, tipo='TAL', fecha=date(2026, 12, 1))
        self.client.post(reverse('revision_vehiculo_editar', args=[revision.pk]),
                         {'tipo': 'ITV', 'fecha': '2026-12-03', 'hora': '10:00', 'motivo': 'ITV Inca'})
        revision.refresh_from_db()
        self.assertEqual((revision.tipo, revision.fecha), ('ITV', date(2026, 12, 3)))

    def test_el_responsable_no_corrige_lecturas(self):
        lectura = Kilometraje.objects.create(vehiculo=self.furgoneta, fecha=date(2026, 11, 1), km=1000, registrado_por=self.peon)
        self.client.force_login(self.peon)
        self.client.post(reverse('kilometraje_editar', args=[lectura.pk]), {'fecha': '2026-11-01', 'km': '5'})
        lectura.refresh_from_db()
        self.assertEqual(lectura.km, 1000)
