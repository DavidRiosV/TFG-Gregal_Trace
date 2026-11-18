"""Trabajos: listados, crear, editar, eliminar, terminar y urgencias."""
from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.db.models import F, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..forms import ProyectoForm, UrgenciaForm
from ..models import Cita, Proyecto
from .comun import clientes_existentes, datos_menu, slug_del_tipo, TIPOS


@permission_required('gestion.view_proyecto')
def lista_proyectos(request, tipo):
    datos_tipo = TIPOS[tipo]
    proyectos = Proyecto.objects.filter(tipo=datos_tipo['codigo'])

    # Filtro por estado: en proceso (por defecto), terminados o todos
    estado = request.GET.get('estado', 'PRO')
    if estado != 'todos':
        proyectos = proyectos.filter(estado=estado)

    # Próxima cita de cada proyecto: la primera de hoy en adelante (las pasadas no cuentan)
    hoy = date.today()
    proyectos = proyectos.annotate(proxima_cita=Min('citas__fecha', filter=Q(citas__fecha__gte=hoy)))

    if estado == 'TER':
        # Terminados: el último que se terminó, primero
        proyectos = proyectos.order_by('-fecha_fin', '-id')
    else:
        # En proceso: primero el que tiene la cita más cercana; los que no tienen ninguna, al final
        proyectos = proyectos.order_by(F('proxima_cita').asc(nulls_last=True), '-fecha_inicio', '-id')

    # Buscador: el texto en el nombre, el cliente O la descripción
    busqueda = request.GET.get('q', '').strip()
    if busqueda:
        proyectos = proyectos.filter(Q(nombre__icontains=busqueda) | Q(cliente__icontains=busqueda) | Q(descripcion__icontains=busqueda))

    # De 25 en 25: con muchos trabajos la página no se hace eterna
    pagina = Paginator(proyectos, 25).get_page(request.GET.get('pagina'))
    parametros = {'estado': estado}
    if busqueda:
        parametros['q'] = busqueda

    # La próxima cita completa (con hora y motivo) de cada proyecto de la página, en una sola consulta
    proyectos = list(pagina)
    siguientes = {}
    for cita in Cita.objects.filter(proyecto__in=proyectos, fecha__gte=hoy).order_by('fecha', 'hora', 'id'):
        siguientes.setdefault(cita.proyecto_id, cita)
    for proyecto in proyectos:
        proyecto.siguiente_cita = siguientes.get(proyecto.pk)

    return render(request, 'gestion/lista_proyectos.html', {
        'proyectos': proyectos,
        'pagina': pagina,
        'base_paginas': '?' + urlencode(parametros) + '&pagina=',
        'titulo': datos_tipo['titulo'],
        'nuevo': datos_tipo['nuevo'],
        'slug': tipo,
        'busqueda': busqueda,
        'estado_actual': estado,
        'seccion': tipo,
        'nav_tipos': datos_menu(),
    })


@permission_required('gestion.add_proyecto')
@permission_required('gestion.change_proyecto')
def proyecto_crear(request, tipo):
    datos_tipo = TIPOS[tipo]

    if request.method == 'POST':
        formulario = ProyectoForm(request.POST)
        if formulario.is_valid():
            # commit=False: crea el objeto sin guardarlo para poder rellenar quién lo creó
            proyecto = formulario.save(commit=False)
            proyecto.creado_por = request.user
            proyecto.save()
            messages.success(request, f'«{proyecto.nombre}» creado en {proyecto.get_tipo_display()}.')
            return redirect('detalle_proyecto', pk=proyecto.pk)
    else:
        # El tipo viene marcado según el listado desde el que se crea
        formulario = ProyectoForm(initial={'tipo': datos_tipo['codigo']})

    return render(request, 'gestion/proyecto_form.html', {
        'formulario': formulario,
        'titulo': datos_tipo['nuevo'],
        'slug_volver': tipo,
        'texto_volver': datos_tipo['titulo'],
        'clientes': clientes_existentes(),
        'nav_tipos': datos_menu(),
        'seccion': tipo,
    })


@permission_required('gestion.change_proyecto')
def proyecto_editar(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)

    if request.method == 'POST':
        # Mismo formulario que crear, pero con instance: modifica este proyecto en vez de crear otro
        formulario = ProyectoForm(request.POST, instance=proyecto)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, f'«{proyecto.nombre}» actualizado.')
            return redirect('detalle_proyecto', pk=proyecto.pk)
    else:
        formulario = ProyectoForm(instance=proyecto)

    slug = slug_del_tipo(proyecto)
    return render(request, 'gestion/proyecto_form.html', {
        'formulario': formulario,
        'proyecto': proyecto,
        'titulo': f'Editar «{proyecto.nombre}»',
        'slug_volver': slug,
        'texto_volver': proyecto.get_tipo_display(),
        'clientes': clientes_existentes(),
        'nav_tipos': datos_menu(),
        'seccion': slug or 'urgencias',
    })


@permission_required('gestion.delete_proyecto')
def proyecto_eliminar(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    # Solo se elimina desde el formulario (POST); si llega por un enlace (GET) vuelve al detalle
    if request.method != 'POST':
        return redirect('detalle_proyecto', pk=proyecto.pk)

    slug = slug_del_tipo(proyecto)
    nombre = proyecto.nombre
    # Si era el último proyecto abierto, se quita de la sesión para que no quede un enlace roto
    if 'ultimo_proyecto' in request.session and request.session['ultimo_proyecto'] == proyecto.pk:
        del request.session['ultimo_proyecto']
        del request.session['ultimo_nombre']
    # Los PDF de sus albaranes se borran del disco; las filas, con on_delete=CASCADE
    for albaran in proyecto.albaranes.all():
        albaran.archivo.delete(save=False)
    # Borra también sus apuntes, notas, citas y albaranes (on_delete=CASCADE)
    proyecto.delete()
    messages.success(request, f'«{nombre}» eliminado.')

    if slug:
        return redirect('lista_proyectos', tipo=slug)
    # Si no tiene apartado es que era una urgencia
    return redirect('urgencias')


@permission_required('gestion.change_proyecto')
def cambiar_estado(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    # Solo cambia si llega por POST (desde el botón); por un enlace (GET) no hace nada
    if request.method == 'POST':
        if proyecto.estado == 'TER':
            proyecto.estado = 'PRO'
            proyecto.fecha_fin = None
            messages.success(request, f'«{proyecto.nombre}» vuelve a estar en proceso.')
        else:
            proyecto.estado = 'TER'
            proyecto.fecha_fin = date.today()
            # Una urgencia terminada pasa al tipo que se eligió al abrirla, con todos sus apuntes
            if proyecto.tipo == 'URG' and proyecto.tipo_destino:
                proyecto.tipo = proyecto.tipo_destino
                proyecto.save()
                messages.success(request, f'Urgencia terminada. Ya está en {proyecto.get_tipo_display()}, con todos sus apuntes.')
                # Se lleva a Oficina al listado donde ha quedado, con el filtro Terminados
                return redirect(reverse('lista_proyectos', args=[slug_del_tipo(proyecto)]) + '?estado=TER')
            messages.success(request, f'«{proyecto.nombre}» marcado como terminado.')
        proyecto.save()
    return redirect('detalle_proyecto', pk=proyecto.pk)


@permission_required('gestion.add_proyecto')
def urgencias(request):
    if request.method == 'POST':
        formulario = UrgenciaForm(request.POST)
        if formulario.is_valid():
            urgencia = formulario.save(commit=False)
            # El tipo y el autor no salen en el formulario: los pone la vista
            urgencia.tipo = 'URG'
            urgencia.creado_por = request.user
            urgencia.save()
            messages.success(request, f'Urgencia «{urgencia.nombre}» creada.')
            return redirect('urgencias')
    else:
        formulario = UrgenciaForm()

    abiertas = Proyecto.objects.filter(tipo='URG', estado='PRO').select_related('creado_por').order_by('-fecha_inicio', '-id')

    return render(request, 'gestion/urgencias.html', {
        'formulario': formulario,
        'urgencias': abiertas,
        'clientes': clientes_existentes(),
        'nav_tipos': datos_menu(),
        'seccion': 'urgencias',
    })
