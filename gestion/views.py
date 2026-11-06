from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, render

from .models import Proyecto

# Apartados de listado: traduce la palabra de la URL al código guardado en la base de datos
TIPOS = {
    'obras': {'codigo': 'OBR', 'titulo': 'Obras', 'corto': 'Obras', 'imagen': 'img/categorias/obras.jpg'},
    'intervenciones': {'codigo': 'INT', 'titulo': 'Intervenciones', 'corto': 'Interv.', 'imagen': 'img/categorias/intervenciones.jpg'},
    'mantenimientos': {'codigo': 'MAN', 'titulo': 'Mantenimientos', 'corto': 'Mant.', 'imagen': 'img/categorias/mantenimientos.jpg'},
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


def index(request):
    return render(request, 'gestion/index.html', {
        'nav_tipos': datos_menu(),
        'seccion': 'inicio',
    })

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
        'busqueda': busqueda,
        'estado_actual': estado,
        'nav_tipos': datos_menu(),
        'seccion': tipo,
    })


def detalle_proyecto(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk)
    consumos = proyecto.consumos.select_related('material', 'trabajador').order_by('-fecha')

    # Total de horas: suma de las cantidades de los apuntes cuya unidad es Hora
    horas = consumos.filter(material__unidad='H').aggregate(Sum('cantidad'))['cantidad__sum']
    if horas is None:
        horas = 0

    # Apartado al que pertenece el proyecto, para el botón de volver y el menú
    slug_volver = None
    for slug, datos in TIPOS.items():
        if datos['codigo'] == proyecto.tipo:
            slug_volver = slug

    return render(request, 'gestion/detalle_proyecto.html', {
        'proyecto': proyecto,
        'consumos': consumos,
        'horas': horas,
        'slug_volver': slug_volver,
        'nav_tipos': datos_menu(),
        'seccion': slug_volver,
    })