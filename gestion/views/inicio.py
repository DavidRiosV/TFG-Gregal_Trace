"""Página de inicio (Oficina y oficiales y peones) y buscador global (Ctrl+K)."""
from datetime import date, datetime, timedelta

from django.contrib.auth.decorators import permission_required
from django.db.models import Max, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from ..models import buscar_materiales, Cita, Consumo, horas_texto, Material, Proyecto, Usuario
from .comun import datos_menu


@permission_required('gestion.view_proyecto')
def index(request):
    # Guarda en la sesión la hora en que entró por primera vez
    if not 'fecha_inicio' in request.session:
        request.session['fecha_inicio'] = datetime.now().strftime('%d/%m/%Y %H:%M')
    hoy = date.today()
    contexto = {
        'nav_tipos': datos_menu(),
        'seccion': 'inicio',
        'hoy': hoy,
        'urgencias_abiertas': Proyecto.objects.filter(tipo='URG', estado='PRO').count(),
        # Citas de hoy y de los próximos 7 días (las ven todos)
        'citas': Cita.objects.filter(fecha__range=(hoy, hoy + timedelta(days=7))).select_related('proyecto')[:8],
    }
    if request.user.has_perm('gestion.change_proyecto'):
        # Oficina: lo que hay que atender. Las próximas citas de dos semanas, agrupadas por día
        proximas = Cita.objects.filter(fecha__range=(hoy, hoy + timedelta(days=14))).select_related('proyecto')
        dias_citas = {}
        for cita in proximas:
            dias_citas.setdefault(cita.fecha, []).append(cita)
        contexto.update({
            'es_oficina': True,
            'en_proceso': Proyecto.objects.exclude(tipo='URG').filter(estado='PRO').count(),
            'citas_hoy': sum(1 for cita in proximas if cita.fecha == hoy),
            'citas_semana': sum(1 for cita in proximas if cita.fecha <= hoy + timedelta(days=7)),
            'dias_citas': [{'fecha': fecha, 'citas': citas} for fecha, citas in dias_citas.items()],
        })
    else:
        # Oficial o peón: sus horas de hoy y de la semana y los trabajos donde ha apuntado hace poco
        lunes = hoy - timedelta(days=hoy.weekday())
        mias = Consumo.objects.filter(material__unidad='H', trabajador=request.user)
        recientes = (Proyecto.objects.filter(consumos__trabajador=request.user, estado='PRO')
                     .annotate(ultimo=Max('consumos__fecha')).order_by('-ultimo')[:5])
        contexto.update({
            'es_oficina': False,
            'horas_hoy_texto': horas_texto(mias.filter(fecha=hoy).aggregate(total=Sum('cantidad'))['total'] or 0),
            'horas_semana_texto': horas_texto(mias.filter(fecha__gte=lunes).aggregate(total=Sum('cantidad'))['total'] or 0),
            'trabajos_recientes': recientes,
        })
    return render(request, 'gestion/index.html', contexto)


# Buscador global (Ctrl+K): trabajos para todos; materiales y empleados, solo Oficina.
# Devuelve JSON, que main.js pinta en el cuadro de búsqueda
@permission_required('gestion.view_proyecto')
def buscar(request):
    texto = request.GET.get('q', '').strip()
    resultados = []
    if len(texto) >= 2:
        proyectos = (Proyecto.objects.filter(Q(nombre__icontains=texto) | Q(cliente__icontains=texto))
                     .order_by('estado', '-fecha_inicio')[:8])
        for proyecto in proyectos:
            resultados.append({
                'grupo': 'Trabajos',
                'titulo': proyecto.nombre,
                'detalle': ' · '.join(filter(None, [proyecto.get_tipo_display(), proyecto.cliente, proyecto.get_estado_display()])),
                'url': reverse('detalle_proyecto', args=[proyecto.pk]),
            })
        if request.user.has_perm('gestion.change_material'):
            for material in buscar_materiales(Material.objects.select_related('categoria'), texto)[:5]:
                resultados.append({
                    'grupo': 'Materiales',
                    'titulo': material.nombre,
                    'detalle': ' · '.join(filter(None, [material.categoria.nombre, material.proveedor])),
                    'url': reverse('material_editar', args=[material.pk]),
                })
        if request.user.has_perm('gestion.view_usuario'):
            empleados = Usuario.objects.filter(rol__in=Usuario.ROLES_OPERARIO).filter(
                Q(first_name__icontains=texto) | Q(last_name__icontains=texto) | Q(username__icontains=texto))[:5]
            for empleado in empleados:
                resultados.append({
                    'grupo': 'Empleados',
                    'titulo': empleado.get_full_name() or empleado.username,
                    'detalle': empleado.get_rol_display(),
                    'url': reverse('empleado_editar', args=[empleado.pk]),
                })
    return JsonResponse({'resultados': resultados})
