"""Estadísticas (Oficina): gastos e ingresos mes a mes y la economía de cada trabajo."""
from datetime import date
from urllib.parse import urlencode

from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from ..economia import CERO, completar, con_importes, mes_a_mes
from ..models import Proyecto
from .comun import datos_menu

# Botones de tipo de trabajo (filtro de la tabla por obra)
TIPOS_ESTADISTICAS = [('', 'Todos'), ('OBR', 'Obras'), ('INT', 'Intervenciones'), ('MAN', 'Mantenimientos'), ('URG', 'Urgencias')]


@permission_required('gestion.change_material')
def estadisticas(request):
    hoy = date.today()
    try:
        anio = int(request.GET.get('anio', hoy.year))
    except ValueError:
        anio = hoy.year
    # Qué tabla se ve: gastos e ingresos o presupuestos
    vista = request.GET.get('vista', 'gastos')
    if vista not in ('gastos', 'presupuestos'):
        vista = 'gastos'
    tipo = request.GET.get('tipo', '')
    if tipo not in dict(TIPOS_ESTADISTICAS):
        tipo = ''
    busqueda = request.GET.get('q', '').strip()

    # ---------- Mes a mes: lo que alimenta el gráfico y las cifras de arriba
    meses = mes_a_mes(anio)
    totales_anio = {
        'gastos': sum((m['gastos'] for m in meses), CERO),
        'ingresos': sum((m['ingresos'] for m in meses), CERO),
        'material': sum((m['material'] for m in meses), CERO),
        'mano_obra': sum((m['mano_obra'] for m in meses), CERO),
    }
    totales_anio['beneficio'] = totales_anio['ingresos'] - totales_anio['gastos']
    # Datos para Chart.js: se pasan a la plantilla y json_script los escribe como JSON
    grafico = {
        'meses': [m['mes'] for m in meses],
        'gastos': [round(float(m['gastos']), 2) for m in meses],
        'ingresos': [round(float(m['ingresos']), 2) for m in meses],
        'beneficio': [round(float(m['beneficio']), 2) for m in meses],
    }

    # ---------- Por obra: los trabajos con movimiento ese año (apuntes, inicio o fin), con sus totales
    con_movimiento = Proyecto.objects.filter(
        Q(consumos__fecha__year=anio) | Q(fecha_inicio__year=anio) | Q(fecha_fin__year=anio)
    ).values_list('pk', flat=True).distinct()
    proyectos = Proyecto.objects.filter(pk__in=list(con_movimiento))
    if tipo:
        proyectos = proyectos.filter(tipo=tipo)
    if busqueda:
        proyectos = proyectos.filter(Q(nombre__icontains=busqueda) | Q(cliente__icontains=busqueda))
    proyectos = [completar(p) for p in con_importes(proyectos)]
    if vista == 'presupuestos':
        # Primero los que tienen presupuesto; dentro, el que menos margen deja arriba
        proyectos.sort(key=lambda p: (p.presupuesto is None, p.beneficio_previsto if p.beneficio_previsto is not None else 0))
    else:
        proyectos.sort(key=lambda p: p.gastado, reverse=True)
    totales_obras = {
        'material': sum((p.material for p in proyectos), CERO),
        'mano_obra': sum((p.mano_obra for p in proyectos), CERO),
        'horas': sum((p.horas for p in proyectos), CERO),
        'gastado': sum((p.gastado for p in proyectos), CERO),
        'ingreso': sum((p.ingreso_real for p in proyectos if p.ingreso_real is not None), CERO),
        # El beneficio total solo de los que ya tienen ingreso
        'beneficio': sum((p.beneficio for p in proyectos if p.beneficio is not None), CERO),
        'presupuesto': sum((p.presupuesto for p in proyectos if p.presupuesto is not None), CERO),
    }
    pagina = Paginator(proyectos, 25).get_page(request.GET.get('pagina'))

    def url_con(**cambios):
        parametros = {'anio': anio, 'vista': vista, 'tipo': tipo, 'q': busqueda}
        parametros.update(cambios)
        return '?' + urlencode({clave: valor for clave, valor in parametros.items() if valor})

    return render(request, 'gestion/estadisticas.html', {
        'anio': anio,
        'vista': vista,
        'tipo_actual': tipo,
        'busqueda': busqueda,
        'meses': meses,
        'totales_anio': totales_anio,
        'grafico': grafico,
        'pagina': pagina,
        'proyectos': list(pagina),
        'totales_obras': totales_obras,
        'num_obras': len(proyectos),
        'base_paginas': url_con(pagina='') + ('&' if url_con(pagina='') != '?' else '') + 'pagina=',
        'url_anio_anterior': url_con(anio=anio - 1, pagina=''),
        'url_anio_siguiente': url_con(anio=anio + 1, pagina=''),
        'botones_vista': [{'texto': texto, 'url': url_con(vista=codigo, pagina=''), 'activo': vista == codigo}
                          for codigo, texto in (('gastos', 'Gastos e ingresos'), ('presupuestos', 'Presupuestos'))],
        'botones_tipo': [{'texto': texto, 'url': url_con(tipo=codigo, pagina=''), 'activo': tipo == codigo}
                         for codigo, texto in TIPOS_ESTADISTICAS],
        'es_este_anio': anio == hoy.year,
        'seccion': 'estadisticas',
        'nav_tipos': datos_menu(),
    })
