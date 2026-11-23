"""Economía de los trabajos (material, mano de obra, ingreso, beneficio) y página de Estadísticas."""
from datetime import date
from decimal import Decimal

from django.urls import reverse

from gestion.economia import mes_a_mes, resumen
from gestion.models import Consumo, Proyecto

from .base import PruebaBase


class Economia(PruebaBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # 10 m de tubería a 3,40 € = 34 € de material; 4 h de oficial a 30 € = 120 € de mano de obra
        Consumo.objects.create(proyecto=cls.obra, material=cls.tuberia, trabajador=cls.oficina,
                               cantidad=Decimal('10'), precio_unitario=Decimal('3.40'), fecha=date(2026, 3, 5))
        Consumo.objects.create(proyecto=cls.obra, material=cls.hora_oficial, trabajador=cls.oficial,
                               cantidad=Decimal('4'), precio_unitario=Decimal('30.00'), fecha=date(2026, 4, 2))

    def test_material_mano_de_obra_y_beneficio(self):
        self.obra.ingreso = Decimal('500')
        self.obra.presupuesto = Decimal('450')
        self.obra.save()
        e = resumen(self.obra)
        self.assertEqual(e.material, Decimal('34.00'))
        self.assertEqual(e.mano_obra, Decimal('120.00'))
        self.assertEqual(e.horas, Decimal('4'))
        self.assertEqual(e.gastado, Decimal('154.00'))
        self.assertEqual(e.beneficio, Decimal('346.00'))
        self.assertEqual(e.beneficio_previsto, Decimal('296.00'))

    def test_subcontratada_cobra_las_horas(self):
        self.obra.subcontratada = True
        self.obra.precio_hora_subcontrata = Decimal('45')
        self.obra.ingreso = Decimal('9999')    # no cuenta: manda el precio por hora
        self.obra.save()
        e = resumen(self.obra)
        self.assertEqual(e.ingreso_real, Decimal('180'))      # 4 h × 45 €/h
        self.assertEqual(e.beneficio, Decimal('26.00'))

    def test_sin_ingreso_no_hay_beneficio_real(self):
        self.obra.presupuesto = Decimal('200')
        self.obra.save()
        e = resumen(self.obra)
        self.assertIsNone(e.ingreso_real)
        self.assertIsNone(e.beneficio)
        self.assertEqual(e.beneficio_previsto, Decimal('46.00'))

    def test_mes_a_mes(self):
        self.obra.ingreso = Decimal('500')
        self.obra.fecha_fin = date(2026, 6, 30)
        self.obra.save()
        meses = mes_a_mes(2026)
        self.assertEqual(meses[2]['material'], Decimal('34.00'))      # marzo
        self.assertEqual(meses[3]['mano_obra'], Decimal('120.00'))    # abril
        self.assertEqual(meses[5]['ingresos'], Decimal('500'))        # junio, cuando se terminó
        self.assertEqual(sum(m['gastos'] for m in meses), Decimal('154.00'))


class PaginaEstadisticas(PruebaBase):
    def test_oficina_la_ve_y_los_operarios_no(self):
        self.client.force_login(self.oficina)
        respuesta = self.client.get(reverse('estadisticas') + '?anio=2026')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context['grafico']['meses']), 12)
        self.assertContains(respuesta, 'datos-grafico')
        self.assertEqual(self.client.get(reverse('estadisticas') + '?vista=presupuestos').status_code, 200)
        self.client.force_login(self.oficial)
        self.assertEqual(self.client.get(reverse('estadisticas')).status_code, 302)

    def test_guardar_la_economia_en_la_ficha(self):
        self.client.force_login(self.oficina)
        url = reverse('detalle_proyecto', args=[self.obra.pk])
        self.client.post(url, {'apunte': 'economia', 'presupuesto': '1200', 'ingreso': '',
                               'subcontratada': 'on', 'precio_hora_subcontrata': '42.50'})
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.presupuesto, Decimal('1200'))
        self.assertTrue(self.obra.subcontratada)
        self.assertEqual(self.obra.precio_hora_subcontrata, Decimal('42.50'))

    def test_subcontratada_sin_precio_no_se_guarda(self):
        self.client.force_login(self.oficina)
        respuesta = self.client.post(reverse('detalle_proyecto', args=[self.obra.pk]),
                                     {'apunte': 'economia', 'subcontratada': 'on', 'precio_hora_subcontrata': ''})
        self.assertContains(respuesta, 'indica el precio por hora')
        self.assertFalse(Proyecto.objects.get(pk=self.obra.pk).subcontratada)

    def test_el_operario_no_ve_la_economia(self):
        self.client.force_login(self.oficial)
        respuesta = self.client.get(reverse('detalle_proyecto', args=[self.obra.pk]))
        self.assertNotContains(respuesta, 'data-pestana="economia"')
        self.client.post(reverse('detalle_proyecto', args=[self.obra.pk]), {'apunte': 'economia', 'presupuesto': '1'})
        self.assertIsNone(Proyecto.objects.get(pk=self.obra.pk).presupuesto)
