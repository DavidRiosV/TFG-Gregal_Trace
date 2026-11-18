"""Lo que comparten varias vistas: los tipos de trabajo, el menú y funciones de ayuda."""
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.urls import reverse

from ..models import Categoria, Material, Proyecto, Tipo


# Apartados de listado: traduce la palabra de la URL al código guardado en la base de datos
TIPOS = {
    'obras': {'codigo': 'OBR', 'titulo': 'Obras', 'corto': 'Obras', 'nuevo': 'Nueva obra', 'imagen': 'img/procesos/obras.jpg'},
    'intervenciones': {'codigo': 'INT', 'titulo': 'Intervenciones', 'corto': 'Interv.', 'nuevo': 'Nueva intervención', 'imagen': 'img/procesos/intervenciones.jpg'},
    'mantenimientos': {'codigo': 'MAN', 'titulo': 'Mantenimientos', 'corto': 'Mant.', 'nuevo': 'Nuevo mantenimiento', 'imagen': 'img/procesos/mantenimientos.jpg'},
}


def datos_menu():
    # Una sola consulta: agrupa los proyectos por tipo y estado y los cuenta (GROUP BY en SQL).
    # Antes eran 6 count() (en proceso y terminados de cada apartado) en cada página.
    conteo = {}
    for fila in Proyecto.objects.values('tipo', 'estado').annotate(n=Count('id')):
        conteo[(fila['tipo'], fila['estado'])] = fila['n']

    nav_tipos = {}
    for slug, datos in TIPOS.items():
        nav_tipos[slug] = {
            'titulo': datos['titulo'],
            'corto': datos['corto'],
            'imagen': datos['imagen'],
            # get(..., 0): si no hay ningún proyecto de ese tipo y estado, la pareja no sale en la consulta
            'en_proceso': conteo.get((datos['codigo'], 'PRO'), 0),
            'terminados': conteo.get((datos['codigo'], 'TER'), 0),
        }
    return nav_tipos


def clientes_existentes():
    # Clientes ya escritos en algún proyecto, para sugerirlos al crear o editar (<datalist>)
    return Proyecto.objects.exclude(cliente='').values_list('cliente', flat=True).distinct().order_by('cliente')


def proveedores_existentes():
    # Proveedores ya escritos en algún material, para sugerirlos al crear o editar (<datalist>)
    return Material.objects.exclude(proveedor='').values_list('proveedor', flat=True).distinct().order_by('proveedor')


def slug_del_tipo(proyecto):
    # Apartado al que pertenece el proyecto ('obras', 'intervenciones'...); None si es una urgencia
    for slug, datos in TIPOS.items():
        if datos['codigo'] == proyecto.tipo:
            return slug
    return None


def filtros_material(request, categoria_por_defecto=''):
    """Lo que ha elegido Oficina para encontrar el material: familia (?categoria=FON),
    tipo (&tipo=3) y texto buscado (?buscar=valvula). Llega por GET o con el formulario (POST)."""
    categoria = request.POST.get('categoria') or request.GET.get('categoria') or categoria_por_defecto
    if not Categoria.objects.filter(pk=categoria).exists():
        categoria = ''
    tipo = request.POST.get('tipo') or request.GET.get('tipo', '')
    if not (tipo.isdigit() and categoria and Tipo.objects.filter(pk=tipo, categoria=categoria).exists()):
        tipo = ''
    busqueda = (request.POST.get('buscar') or request.GET.get('buscar', '')).strip()
    tipos = []
    if categoria:
        # Tipos de la familia con cuántos materiales tiene cada uno (las horas no salen aquí)
        tipos = (Tipo.objects.filter(categoria=categoria)
                 .annotate(n=Count('materiales', filter=~Q(materiales__unidad='H')))
                 .filter(n__gt=0).order_by('nombre'))
    return {
        'categorias': Categoria.objects.values_list('codigo', 'nombre'),
        'categoria_actual': categoria,
        'tipos_familia': tipos,
        'tipo_actual': tipo,
        'busqueda_material': busqueda,
    }


def url_con_filtros(pk, filtros, ancla):
    # URL del detalle con los mismos filtros, para seguir apuntando desde el mismo sitio
    parametros = {}
    if filtros['busqueda_material']:
        parametros['buscar'] = filtros['busqueda_material']
    elif filtros['categoria_actual']:
        parametros['categoria'] = filtros['categoria_actual']
        if filtros['tipo_actual']:
            parametros['tipo'] = filtros['tipo_actual']
    url = reverse('detalle_proyecto', args=[pk])
    if parametros:
        url += '?' + urlencode(parametros)
    return url + ancla
