"""Citas: apartado de Oficina, borrarlas desde el proyecto y calendario con Outlook."""
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from ..calendario import descargar_ics, dias_del_evento, leer_eventos, url_outlook_web
from ..forms import CitaGestionForm
from ..models import Asignacion, Cita, RevisionVehiculo, Usuario
from .comun import datos_menu


@permission_required('gestion.delete_cita')
def cita_eliminar(request, pk):
    cita = get_object_or_404(Cita.objects.select_related('proyecto'), pk=pk)
    if request.method == 'POST':
        fecha = cita.fecha
        cita.delete()
        messages.success(request, f'Cita del {fecha:%d/%m/%Y} eliminada.')
        # Desde el apartado Citas se vuelve a la lista; desde un proyecto, a sus citas
        volver = request.POST.get('volver', '')
        if volver and url_has_allowed_host_and_scheme(volver, allowed_hosts={request.get_host()}):
            return redirect(volver)
    return redirect(reverse('detalle_proyecto', args=[cita.proyecto.pk]) + '#citas')


# ---------------------------------------------------------------------------
# Calendario (Oficina): el calendario de Outlook de la empresa junto a las citas de los proyectos
# ---------------------------------------------------------------------------
DIAS_CALENDARIO = 14


@permission_required('gestion.change_proyecto')
def calendario(request):
    hoy = date.today()
    # Primer día que se enseña (?desde=2026-11-10); si no llega o no es una fecha, hoy
    try:
        desde = datetime.strptime(request.GET.get('desde', ''), '%Y-%m-%d').date()
    except ValueError:
        desde = hoy
    hasta = desde + timedelta(days=DIAS_CALENDARIO - 1)

    # Qué se ve: todo, solo Outlook, solo las citas de los proyectos o dónde está cada trabajador
    ver = request.GET.get('ver', 'todo')
    if ver not in ('todo', 'outlook', 'citas', 'trabajadores', 'vehiculos'):
        ver = 'todo'

    por_dia = {}
    for numero in range(DIAS_CALENDARIO):
        por_dia[desde + timedelta(days=numero)] = []

    error = ''
    if ver in ('todo', 'outlook'):
        try:
            eventos = leer_eventos(descargar_ics())
        except (OSError, ValueError):
            # Sin internet, enlace caducado o calendario despublicado: se avisa y se siguen viendo las citas
            eventos = []
            error = 'Ahora mismo no se puede leer el calendario de Outlook. Se muestran solo las citas de los proyectos.'
        for evento in eventos:
            dias = list(dias_del_evento(evento))
            for numero, dia in enumerate(dias):
                if dia in por_dia:
                    # Un evento de varios días sale en cada uno; a partir del segundo, como «todo el día»
                    primer_dia = numero == 0
                    con_hora = not evento['todo_el_dia'] and primer_dia
                    por_dia[dia].append({
                        'fuente': 'outlook',
                        'titulo': evento['titulo'] or '(Sin título)',
                        'lugar': evento['lugar'],
                        'inicio': evento['inicio'] if con_hora else None,
                        'fin': evento['fin'] if con_hora and evento['fin'].date() == dia else None,
                        'varios_dias': f'Día {numero + 1} de {len(dias)}' if len(dias) > 1 else '',
                        'orden': evento['inicio'].strftime('%H:%M') if con_hora else '',
                    })

    if ver in ('todo', 'citas'):
        for cita in Cita.objects.filter(fecha__range=(desde, hasta)).select_related('proyecto'):
            por_dia[cita.fecha].append({
                'fuente': 'cita',
                'titulo': cita.motivo or 'Cita',
                'proyecto': cita.proyecto,
                'inicio': cita.hora,
                'orden': cita.hora.strftime('%H:%M') if cita.hora else '',
            })

    # Vehículos: revisiones de taller e ITV
    if ver in ('todo', 'vehiculos'):
        for revision in RevisionVehiculo.objects.filter(fecha__range=(desde, hasta)).select_related('vehiculo'):
            por_dia[revision.fecha].append({
                'fuente': 'vehiculo',
                'titulo': f'{revision.get_tipo_display()} · {revision.vehiculo.modelo}',
                'vehiculo': revision.vehiculo,
                'motivo': revision.motivo,
                'inicio': revision.hora,
                'orden': revision.hora.strftime('%H:%M') if revision.hora else '',
            })

    # Trabajadores: a qué trabajo va cada oficial o peón (agenda de empleados)
    sin_agendar = {}
    if ver in ('todo', 'trabajadores'):
        asignaciones = (Asignacion.objects.filter(fecha__range=(desde, hasta))
                        .select_related('empleado', 'proyecto').order_by('fecha', 'franja', 'empleado__first_name'))
        for asignacion in asignaciones:
            por_dia[asignacion.fecha].append({
                'fuente': 'trabajador',
                'titulo': asignacion.empleado.get_full_name() or asignacion.empleado.username,
                'empleado': asignacion.empleado,
                'proyecto': asignacion.proyecto,
                'nota': asignacion.nota,
                'franja': asignacion.get_franja_display(),
                # Todo el día arriba, luego la mañana y luego la tarde
                'orden': {'DIA': '', 'MAN': '08:00', 'TAR': '15:00'}[asignacion.franja],
            })
        if ver == 'trabajadores':
            # Quién no tiene nada agendado cada día (oficiales y peones en activo), para verlo de un vistazo
            plantilla = list(Usuario.objects.filter(rol__in=Usuario.ROLES_OPERARIO, is_active=True)
                             .order_by('first_name', 'last_name'))
            for dia in por_dia:
                ocupados = {a.empleado_id for a in asignaciones if a.fecha == dia}
                sin_agendar[dia] = [e for e in plantilla if e.pk not in ocupados]

    # Días con algo (y hoy siempre); dentro de cada día, primero lo de todo el día y luego por hora.
    # En «Trabajadores» salen todos los días de lunes a sábado, para ver también quién está libre
    dias = []
    for dia, elementos in por_dia.items():
        laborable = ver == 'trabajadores' and dia.weekday() < 6
        if elementos or dia == hoy or laborable:
            elementos.sort(key=lambda elemento: elemento['orden'])
            dias.append({'fecha': dia, 'elementos': elementos, 'es_hoy': dia == hoy,
                         'sin_agendar': sin_agendar.get(dia, [])})

    def url_desde(fecha):
        parametros = {'desde': fecha.isoformat()}
        if ver != 'todo':
            parametros['ver'] = ver
        return '?' + urlencode(parametros)

    return render(request, 'gestion/calendario.html', {
        'dias': dias,
        'desde': desde,
        'hasta': hasta,
        'ver_actual': ver,
        'error': error,
        'url_anterior': url_desde(desde - timedelta(days=DIAS_CALENDARIO)),
        'url_siguiente': url_desde(desde + timedelta(days=DIAS_CALENDARIO)),
        'url_hoy': url_desde(hoy),
        'es_desde_hoy': desde == hoy,
        'url_outlook': url_outlook_web(),
        'seccion': 'calendario',
        'nav_tipos': datos_menu(),
    })


# ---------------------------------------------------------------------------
# Citas (Oficina): agendar, revisar y cambiar las citas de todos los trabajos en un solo sitio.
# El calendario las enseña junto a Outlook; aquí se gestionan.
# ---------------------------------------------------------------------------
@permission_required('gestion.change_cita')
def lista_citas(request):
    hoy = date.today()
    ver = request.GET.get('ver', 'proximas')
    if ver not in ('proximas', 'pasadas', 'todas'):
        ver = 'proximas'
    busqueda = request.GET.get('q', '').strip()

    if request.method == 'POST':
        formulario = CitaGestionForm(request.POST)
        if formulario.is_valid():
            cita = formulario.save(commit=False)
            cita.creada_por = request.user
            cita.save()
            messages.success(request, f'Cita del {cita.fecha:%d/%m/%Y} añadida a {cita.proyecto.nombre} ({cita.dias()}).')
            return redirect(request.get_full_path())
    else:
        # Si se llega desde un proyecto (?proyecto=12), ya sale elegido
        inicial = {'fecha': hoy}
        if request.GET.get('proyecto', '').isdigit():
            inicial['proyecto'] = int(request.GET['proyecto'])
        formulario = CitaGestionForm(initial=inicial)

    citas = Cita.objects.select_related('proyecto', 'creada_por')
    if ver == 'proximas':
        citas = citas.filter(fecha__gte=hoy)
    elif ver == 'pasadas':
        citas = citas.filter(fecha__lt=hoy).order_by('-fecha', '-hora', '-id')
    if busqueda:
        citas = citas.filter(Q(motivo__icontains=busqueda) | Q(proyecto__nombre__icontains=busqueda)
                             | Q(proyecto__cliente__icontains=busqueda))

    totales = {
        'proximas': Cita.objects.filter(fecha__gte=hoy).count(),
        'pasadas': Cita.objects.filter(fecha__lt=hoy).count(),
        'todas': Cita.objects.count(),
    }
    botones = []
    for codigo, texto in (('proximas', 'Próximas'), ('pasadas', 'Pasadas'), ('todas', 'Todas')):
        parametros = {'ver': codigo}
        if busqueda:
            parametros['q'] = busqueda
        botones.append({'texto': texto, 'n': totales[codigo], 'url': '?' + urlencode(parametros), 'activo': codigo == ver})

    pagina = Paginator(citas, 25).get_page(request.GET.get('pagina'))
    parametros = {'ver': ver}
    if busqueda:
        parametros['q'] = busqueda
    return render(request, 'gestion/citas.html', {
        'formulario': formulario,
        'pagina': pagina,
        'citas': list(pagina),
        'base_paginas': '?' + urlencode(parametros) + '&pagina=',
        'botones_ver': botones,
        'ver_actual': ver,
        'busqueda': busqueda,
        'hoy': hoy,
        'seccion': 'citas',
        'nav_tipos': datos_menu(),
    })


@permission_required('gestion.change_cita')
def cita_editar(request, pk):
    cita = get_object_or_404(Cita.objects.select_related('proyecto'), pk=pk)
    if request.method == 'POST':
        formulario = CitaGestionForm(request.POST, instance=cita)
        if formulario.is_valid():
            cita = formulario.save()
            messages.success(request, f'Cita del {cita.fecha:%d/%m/%Y} guardada ({cita.dias()}).')
            return redirect('lista_citas')
    else:
        formulario = CitaGestionForm(instance=cita)
    return render(request, 'gestion/cita_form.html', {
        'formulario': formulario,
        'cita': cita,
        'seccion': 'citas',
        'nav_tipos': datos_menu(),
    })
