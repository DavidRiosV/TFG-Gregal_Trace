"""
Economía de los trabajos (Oficina): lo gastado en material y en mano de obra, lo ingresado y el beneficio.

- Material: los apuntes que no son horas (cantidad × precio guardado en el apunte).
- Mano de obra: los apuntes de horas (horas × precio de la hora guardado en el apunte).
- Gastado = material + mano de obra.
- Ingreso: si el trabajo está subcontratado por horas, las horas apuntadas × su precio por hora;
  si no, el ingreso que escribe Oficina en el proyecto.
- Beneficio = ingreso − gastado (solo si ya hay ingreso). Con presupuesto, también el beneficio
  previsto = presupuesto − gastado.
"""
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce, ExtractMonth

from .models import Consumo, Proyecto

CERO = Decimal('0.00')
MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

# Importe de cada apunte: cantidad × precio. ExpressionWrapper dice a Django qué tipo de dato sale
IMPORTE = ExpressionWrapper(F('consumos__cantidad') * F('consumos__precio_unitario'),
                            output_field=DecimalField(max_digits=14, decimal_places=2))
ES_HORA = Q(consumos__material__unidad='H')


def suma(expresion, filtro):
    """SUM con filtro; si no hay apuntes, 0 en vez de None (Coalesce)."""
    return Coalesce(Sum(expresion, filter=filtro), Value(CERO), output_field=DecimalField(max_digits=14, decimal_places=2))


def con_importes(proyectos):
    """Añade a cada proyecto material, mano_obra y horas en una sola consulta (GROUP BY)."""
    return proyectos.annotate(
        material=suma(IMPORTE, ~ES_HORA),
        mano_obra=suma(IMPORTE, ES_HORA),
        horas=suma('consumos__cantidad', ES_HORA),
    )


def completar(proyecto):
    """Con los importes ya calculados, pone gastado, ingreso_real, beneficio y beneficio_previsto."""
    proyecto.gastado = proyecto.material + proyecto.mano_obra
    if proyecto.subcontratada and proyecto.precio_hora_subcontrata:
        proyecto.ingreso_real = proyecto.horas * proyecto.precio_hora_subcontrata
    else:
        # None: todavía no se ha indicado lo ingresado (por ejemplo, un trabajo en proceso)
        proyecto.ingreso_real = proyecto.ingreso
    # Sin ingreso no hay beneficio real: solo el previsto, si hay presupuesto
    proyecto.beneficio = proyecto.ingreso_real - proyecto.gastado if proyecto.ingreso_real is not None else None
    proyecto.beneficio_previsto = proyecto.presupuesto - proyecto.gastado if proyecto.presupuesto is not None else None
    return proyecto


def resumen(proyecto):
    """Economía de un solo proyecto (para su pestaña en la ficha)."""
    return completar(con_importes(Proyecto.objects.filter(pk=proyecto.pk)).get())


def mes_a_mes(anio):
    """Gastos (material y mano de obra) e ingresos de cada mes del año, para el gráfico de barras."""
    meses = [{'mes': MESES[numero], 'material': CERO, 'mano_obra': CERO, 'ingresos': CERO} for numero in range(12)]
    importe = ExpressionWrapper(F('cantidad') * F('precio_unitario'), output_field=DecimalField(max_digits=14, decimal_places=2))

    # Gastos: los apuntes del año agrupados por mes, separando horas y material
    apuntes = Consumo.objects.filter(fecha__year=anio).annotate(numero=ExtractMonth('fecha'))
    # (los nombres de las sumas no pueden coincidir con el campo «material» del apunte)
    for fila in apuntes.values('numero').annotate(
            en_material=Sum(importe, filter=~Q(material__unidad='H')),
            en_mano_obra=Sum(importe, filter=Q(material__unidad='H'))).order_by():
        meses[fila['numero'] - 1]['material'] = fila['en_material'] or CERO
        meses[fila['numero'] - 1]['mano_obra'] = fila['en_mano_obra'] or CERO

    # Ingresos de los subcontratados por horas: cada mes, sus horas por el precio por hora
    horas_sub = apuntes.filter(material__unidad='H', proyecto__subcontratada=True,
                               proyecto__precio_hora_subcontrata__isnull=False)
    precio_sub = ExpressionWrapper(F('cantidad') * F('proyecto__precio_hora_subcontrata'),
                                   output_field=DecimalField(max_digits=14, decimal_places=2))
    for fila in horas_sub.values('numero').annotate(total=Sum(precio_sub)).order_by():
        meses[fila['numero'] - 1]['ingresos'] += fila['total'] or CERO

    # Ingresos del resto: el del proyecto, en el mes en que se terminó (o en el que empezó si sigue abierto)
    fijos = Proyecto.objects.filter(ingreso__isnull=False).exclude(subcontratada=True, precio_hora_subcontrata__isnull=False)
    for proyecto in fijos:
        fecha = proyecto.fecha_fin or proyecto.fecha_inicio
        if fecha and fecha.year == anio:
            meses[fecha.month - 1]['ingresos'] += proyecto.ingreso

    for mes in meses:
        mes['gastos'] = mes['material'] + mes['mano_obra']
        mes['beneficio'] = mes['ingresos'] - mes['gastos']
    return meses
