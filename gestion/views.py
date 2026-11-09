from django.db.models import Q, Sum
from django.contrib.auth import login
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import permission_required
from django.urls import reverse
from datetime import date, datetime

from .forms import RegistroForm,ProyectoForm,UrgenciaForm
from .models import Oficina, Operario, Proyecto, Usuario


# Apartados de listado: traduce la palabra de la URL al código guardado en la base de datos
TIPOS = {
    'obras': {'codigo': 'OBR', 'titulo': 'Obras', 'corto': 'Obras', 'nuevo': 'Nueva obra', 'imagen': 'img/categorias/obras.jpg'},
    'intervenciones': {'codigo': 'INT', 'titulo': 'Intervenciones', 'corto': 'Interv.', 'nuevo': 'Nueva intervención', 'imagen': 'img/categorias/intervenciones.jpg'},
    'mantenimientos': {'codigo': 'MAN', 'titulo': 'Mantenimientos', 'corto': 'Mant.', 'nuevo': 'Nuevo mantenimiento', 'imagen': 'img/categorias/mantenimientos.jpg'},
}

def datos_menu():
    nav_tipos = {}
    for slug, datos in TIPOS.items():
        nav_tipos[slug] = {
            'titulo': datos['titulo'],
            'corto': datos['corto'],
            'imagen': datos['imagen'],
            'en_proceso': Proyecto.objects.filter(tipo=datos['codigo'], estado='PRO').count(),
            'terminados': Proyecto.objects.filter(tipo=datos['codigo'], estado='TER').count(),
        }
    return nav_tipos

@permission_required('gestion.view_proyecto')
def index(request):
    # Guarda en la sesión la hora en que entró por primera vez
    if not 'fecha_inicio' in request.session:
        request.session['fecha_inicio'] = datetime.now().strftime('%d/%m/%Y %H:%M')
    return render(request, 'gestion/index.html', {
        'nav_tipos': datos_menu(),
        'seccion': 'inicio',
    })

@permission_required('gestion.view_proyecto')
def lista_proyectos(request, tipo):
    datos_tipo = TIPOS[tipo]
    proyectos = Proyecto.objects.filter(tipo=datos_tipo['codigo']).order_by('-fecha_inicio')

    # Filtro por estado: en proceso (por defecto), terminados o todos
    estado = request.GET.get('estado', 'PRO')
    if estado != 'todos':
        proyectos = proyectos.filter(estado=estado)

    # Buscador: el texto en el nombre O en la descripción
    busqueda = request.GET.get('q', '')
    if busqueda:
        proyectos = proyectos.filter(Q(nombre__icontains=busqueda) | Q(descripcion__icontains=busqueda))

    return render(request, 'gestion/lista_proyectos.html', {
        'proyectos': proyectos,
        'titulo': datos_tipo['titulo'],
        'nuevo': datos_tipo['nuevo'],
        'slug': tipo,
        'busqueda': busqueda,
        'estado_actual': estado,
        'seccion': tipo,
        'nav_tipos': datos_menu(),
    })

def slug_del_tipo(proyecto):
    # Apartado al que pertenece el proyecto ('obras', 'intervenciones'...); None si es una urgencia
    for slug, datos in TIPOS.items():
        if datos['codigo'] == proyecto.tipo:
            return slug
    return None

@permission_required('gestion.view_proyecto')
def detalle_proyecto(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    # Recuerda el último proyecto abierto para ofrecerlo en la portada
    request.session['ultimo_proyecto'] = proyecto.pk
    request.session['ultimo_nombre'] = proyecto.nombre
    consumos = proyecto.consumos.select_related('material', 'trabajador').order_by('-fecha')

    # Total de horas: suma de las cantidades de los apuntes cuya unidad es Hora
    horas = consumos.filter(material__unidad='H').aggregate(Sum('cantidad'))['cantidad__sum']
    if horas is None:
        horas = 0

    # Apartado al que pertenece el proyecto, para el botón de volver y el menú
    slug_volver = slug_del_tipo(proyecto)

    return render(request, 'gestion/detalle_proyecto.html', {
        'proyecto': proyecto,
        'consumos': consumos,
        'horas': horas,
        'slug_volver': slug_volver,
        'nav_tipos': datos_menu(),
        'seccion': slug_volver or 'urgencias',
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
            return redirect('detalle_proyecto', pk=proyecto.pk)
    else:
        # El tipo viene marcado según el listado desde el que se crea
        formulario = ProyectoForm(initial={'tipo': datos_tipo['codigo']})

    return render(request, 'gestion/proyecto_form.html', {
        'formulario': formulario,
        'titulo': datos_tipo['nuevo'],
        'slug_volver': tipo,
        'texto_volver': datos_tipo['titulo'],
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
    # Si era el último proyecto abierto, se quita de la sesión para que no quede un enlace roto
    if 'ultimo_proyecto' in request.session and request.session['ultimo_proyecto'] == proyecto.pk:
        del request.session['ultimo_proyecto']
        del request.session['ultimo_nombre']
    # Borra también sus apuntes (on_delete=CASCADE en Consumo)
    proyecto.delete()

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
        else:
            proyecto.estado = 'TER'
            proyecto.fecha_fin = date.today()
            # Una urgencia terminada pasa al tipo que se eligió al abrirla, con todos sus apuntes
            if proyecto.tipo == 'URG' and proyecto.tipo_destino:
                proyecto.tipo = proyecto.tipo_destino
                proyecto.save()
                # Se lleva a Oficina al listado donde ha quedado, con el filtro Terminados
                return redirect(reverse('lista_proyectos', args=[slug_del_tipo(proyecto)]) + '?estado=TER')
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
            return redirect('urgencias')
    else:
        formulario = UrgenciaForm()

    abiertas = Proyecto.objects.filter(tipo='URG', estado='PRO').select_related('creado_por').order_by('-fecha_inicio', '-id')

    return render(request, 'gestion/urgencias.html', {
        'formulario': formulario,
        'urgencias': abiertas,
        'nav_tipos': datos_menu(),
        'seccion': 'urgencias',
    })

def registrar_usuario(request):
    # Si ya ha iniciado sesión no tiene sentido registrarse
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == 'POST':
        formulario = RegistroForm(request.POST)
        if formulario.is_valid():
            user = formulario.save()
            # Según el rol elegido se crea un modelo u otro y se mete en su grupo de permisos
            rol = int(formulario.cleaned_data.get('rol'))
            if rol == Usuario.OPERARIO:
                operario = Operario.objects.create(usuario=user)
                operario.save()
                grupo = Group.objects.get(name='Operarios')
                grupo.user_set.add(user)
            elif rol == Usuario.OFICINA:
                oficina = Oficina.objects.create(usuario=user)
                oficina.save()
                grupo = Group.objects.get(name='Oficina')
                grupo.user_set.add(user)
            # Entra directamente sin tener que hacer login
            login(request, user)
            return redirect('index')
    else:
        formulario = RegistroForm()

    return render(request, 'registration/signup.html', {'formulario': formulario})
