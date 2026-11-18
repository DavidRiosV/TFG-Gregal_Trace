"""Apuntar horas: puesto del rol, precio según puesto + campo y varias líneas."""
from decimal import Decimal

from django.urls import reverse

from gestion.models import Consumo, TarifaHora

from .base import PruebaBase


class ApuntarHoras(PruebaBase):
    def apuntar(self, usuario, **datos):
        self.client.force_login(usuario)
        datos = {'apunte': 'horas', 'fecha': '2026-11-17', **datos}
        return self.client.post(reverse('detalle_proyecto', args=[self.obra.pk]), datos)

    def test_el_peon_apunta_siempre_como_peon(self):
        # Aunque envíe «Hora Oficial» a mano, se guarda el puesto de su rol
        self.apuntar(self.peon, material=self.hora_oficial.pk, campo=self.electricidad.pk, cantidad='2.00')
        apunte = Consumo.objects.get()
        self.assertEqual(apunte.material, self.hora_peon)
        self.assertEqual(apunte.trabajador, self.peon)

    def test_precio_de_la_tarifa(self):
        TarifaHora.objects.create(puesto=self.hora_oficial, campo=self.electricidad, precio=Decimal('34.00'))
        self.apuntar(self.oficial, material=self.hora_oficial.pk, campo=self.electricidad.pk, cantidad='3.00')
        apunte = Consumo.objects.get()
        self.assertEqual(apunte.precio_unitario, Decimal('34.00'))
        self.assertEqual(apunte.total(), Decimal('102.00'))

    def test_sin_tarifa_usa_el_precio_base(self):
        self.apuntar(self.oficial, material=self.hora_oficial.pk, campo=self.electricidad.pk, cantidad='1.00')
        self.assertEqual(Consumo.objects.get().precio_unitario, self.hora_oficial.precio)

    def test_cambiar_la_tarifa_no_cambia_lo_apuntado(self):
        tarifa = TarifaHora.objects.create(puesto=self.hora_oficial, campo=self.electricidad, precio=Decimal('30.00'))
        self.apuntar(self.oficial, material=self.hora_oficial.pk, campo=self.electricidad.pk, cantidad='1.00')
        tarifa.precio = Decimal('50.00')
        tarifa.save()
        self.assertEqual(Consumo.objects.get().precio_unitario, Decimal('30.00'))

    def test_el_campo_es_obligatorio(self):
        respuesta = self.apuntar(self.oficial, material=self.hora_oficial.pk, cantidad='1.00')
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Elige el campo del trabajo.')
        self.assertFalse(Consumo.objects.exists())

    def test_tramos_de_15_minutos(self):
        self.apuntar(self.oficial, material=self.hora_oficial.pk, campo=self.electricidad.pk, cantidad='1.10')
        self.assertFalse(Consumo.objects.exists())

    def test_varias_lineas_a_la_vez(self):
        self.apuntar(self.oficial, material=self.hora_oficial.pk, cantidad='1.00',
                     linea_material=[self.hora_oficial.pk, self.hora_oficial.pk],
                     linea_campo=[self.electricidad.pk, self.electricidad.pk],
                     linea_cantidad=['4.00', '2.50'])
        self.assertEqual(Consumo.objects.count(), 2)
        self.assertEqual(sum(c.cantidad for c in Consumo.objects.all()), Decimal('6.50'))

    def test_si_una_linea_falla_no_se_guarda_ninguna(self):
        self.apuntar(self.oficial, material=self.hora_oficial.pk, cantidad='1.00',
                     linea_material=[self.hora_oficial.pk, self.hora_oficial.pk],
                     linea_campo=[self.electricidad.pk, ''],
                     linea_cantidad=['4.00', '2.00'])
        self.assertFalse(Consumo.objects.exists())

    def test_en_un_proyecto_terminado_no_se_apunta(self):
        self.client.force_login(self.oficial)
        self.client.post(reverse('detalle_proyecto', args=[self.terminada.pk]),
                         {'apunte': 'horas', 'material': self.hora_oficial.pk, 'campo': self.electricidad.pk,
                          'cantidad': '1.00', 'fecha': '2026-11-17'})
        self.assertFalse(Consumo.objects.exists())

    def test_el_operario_no_apunta_material(self):
        self.client.force_login(self.oficial)
        self.client.post(reverse('detalle_proyecto', args=[self.obra.pk]),
                         {'apunte': 'material', 'material': self.tuberia.pk, 'cantidad': '2', 'fecha': '2026-11-17'})
        self.assertFalse(Consumo.objects.exists())

    def test_oficina_apunta_material_con_su_precio(self):
        self.client.force_login(self.oficina)
        self.client.post(reverse('detalle_proyecto', args=[self.obra.pk]) + f'?categoria={self.tuberia.categoria_id}',
                         {'apunte': 'material', 'categoria': self.tuberia.categoria_id, 'material': self.tuberia.pk,
                          'cantidad': '10', 'fecha': '2026-11-17'})
        apunte = Consumo.objects.get()
        self.assertEqual(apunte.total(), Decimal('34.00'))
