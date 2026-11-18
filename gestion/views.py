from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import Group
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models import ProtectedError, Count, F, Max, Min, Q, Sum
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .calendario import descargar_ics, dias_del_evento, leer_eventos, url_outlook_web
from .forms import (AlbaranForm, CampoHoraForm, CategoriaForm, EmpleadoForm, PuestoForm, TarifaForm, CitaForm, CitaGestionForm, ConsumoForm, HorasForm, MaterialForm, NotaForm,
                    ProyectoForm, RegistroForm, TipoForm, UrgenciaForm)
from .models import (Albaran, CampoHora, Categoria, TarifaHora, precio_hora, Cita, Consumo, Material, Nota, Oficina, Operario, Proyecto, Tipo, Usuario,
                     buscar_materiales, horas_texto, sin_tildes)


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

def puesto_del_rol(usuario):
    """Puesto con el que apunta horas un oficial («Hora Oficial») o un peón («Hora Peón»).
    None para Oficina y el administrador, que sí eligen el puesto (o si ese puesto no existe)."""
    nombre = {Usuario.OFICIAL: 'Hora Oficial', Usuario.PEON: 'Hora Peón'}.get(usuario.rol)
    return Material.objects.filter(unidad='H', nombre=nombre).first() if nombre else None


def lineas_de_horas(post):
    """Datos de cada línea de un apunte de horas. Con JavaScript llegan varias líneas en listas
    (linea_material, linea_campo, linea_cantidad); sin líneas, se apunta lo elegido en el formulario."""
    materiales = post.getlist('linea_material')
    if not materiales:
        return [post]
    campos = post.getlist('linea_campo')
    cantidades = post.getlist('linea_cantidad')
    lineas = []
    for numero, material in enumerate(materiales):
        lineas.append({
            'material': material,
            'campo': campos[numero] if numero < len(campos) else '',
            'cantidad': cantidades[numero] if numero < len(cantidades) else '',
            'fecha': post.get('fecha'),
        })
    return lineas


@permission_required('gestion.view_proyecto')
def detalle_proyecto(request, pk):
    proyecto = get_object_or_404(Proyecto.objects.select_related('creado_por'), pk=pk)
    # Recuerda el último proyecto abierto para ofrecerlo en la portada
    request.session['ultimo_proyecto'] = proyecto.pk
    request.session['ultimo_nombre'] = proyecto.nombre

    # Quién puede hacer qué: los operarios apuntan horas, notas y albaranes; el material lo apunta Oficina.
    # En un proyecto terminado ya no se apunta nada (pero sí notas, albaranes y citas)
    es_oficina = request.user.has_perm('gestion.change_proyecto')
    puede_apuntar = request.user.has_perm('gestion.add_consumo') and proyecto.estado == 'PRO'
    puede_apuntar_material = puede_apuntar and es_oficina

    filtros = filtros_material(request)
    opciones = {'categoria': filtros['categoria_actual'], 'tipo': filtros['tipo_actual'], 'busqueda': filtros['busqueda_material']}

    formulario = ConsumoForm(**opciones)
    # Oficiales y peones no eligen puesto: se apunta el de su rol
    puesto_fijo = puesto_del_rol(request.user)
    formulario_horas = HorasForm(puesto_fijo=puesto_fijo)
    formulario_nota = NotaForm()
    formulario_albaran = AlbaranForm()
    formulario_cita = CitaForm()
    # Pestaña que se abre al cargar: Horas si puede apuntar; si no, Apuntes.
    # Si un formulario vuelve con errores, se abre su pestaña
    pestana = 'horas' if puede_apuntar else 'apuntes'

    if request.method == 'POST':
        # La página tiene varios formularios: un campo oculto «apunte» dice cuál se ha enviado
        enviado = request.POST.get('apunte')

        if enviado == 'cita' and request.user.has_perm('gestion.add_cita'):
            pestana = 'citas'
            formulario_cita = CitaForm(request.POST)
            if formulario_cita.is_valid():
                cita = formulario_cita.save(commit=False)
                cita.proyecto = proyecto
                cita.creada_por = request.user
                cita.save()
                messages.success(request, f'Cita añadida para el {cita.fecha:%d/%m/%Y} ({cita.dias()}).')
                return redirect(reverse('detalle_proyecto', args=[proyecto.pk]) + '#citas')

        elif enviado == 'nota' and request.user.has_perm('gestion.add_nota'):
            pestana = 'notas'
            formulario_nota = NotaForm(request.POST)
            if formulario_nota.is_valid():
                nota = formulario_nota.save(commit=False)
                nota.proyecto = proyecto
                nota.autor = request.user
                nota.save()
                messages.success(request, 'Nota añadida al proyecto.')
                return redirect(reverse('detalle_proyecto', args=[proyecto.pk]) + '#notas')

        elif enviado == 'albaran' and request.user.has_perm('gestion.add_albaran'):
            pestana = 'albaranes'
            # El archivo llega en request.FILES (formulario con enctype multipart/form-data)
            formulario_albaran = AlbaranForm(request.POST, request.FILES)
            if formulario_albaran.is_valid():
                albaran = formulario_albaran.save(commit=False)
                albaran.proyecto = proyecto
                albaran.subido_por = request.user
                albaran.save()
                messages.success(request, f'Albarán «{albaran.descripcion or albaran.nombre_archivo()}» subido.')
                return redirect(reverse('detalle_proyecto', args=[proyecto.pk]) + '#albaranes')

        elif enviado == 'horas' and puede_apuntar:
            # Un apunte de horas puede llevar varias líneas (Oficial · Electricidad 4 h + Oficial · Fontanería 2 h).
            # Cada línea se valida con su propio HorasForm; si alguna falla no se guarda ninguna.
            formularios = [HorasForm(datos, puesto_fijo=puesto_fijo) for datos in lineas_de_horas(request.POST)]
            invalidos = [f for f in formularios if not f.is_valid()]
            if formularios and not invalidos:
                textos = []
                for formulario_linea in formularios:
                    consumo = formulario_linea.save(commit=False)
                    consumo.proyecto = proyecto
                    consumo.trabajador = request.user
                    # El precio sale de la combinación puesto + campo y se congela en el apunte
                    consumo.precio_unitario = precio_hora(consumo.material, consumo.campo)
                    consumo.save()
                    textos.append(f'{consumo.cantidad_texto()} de {consumo.descripcion()}')
                messages.success(request, 'Apuntado: ' + '; '.join(textos) + '.')
                return redirect(reverse('detalle_proyecto', args=[proyecto.pk]) + '#horas')
            formulario_horas = invalidos[0] if invalidos else HorasForm(request.POST, puesto_fijo=puesto_fijo)
            if len(formularios) > 1:
                messages.error(request, 'Alguna línea no es válida y no se ha apuntado ninguna. Revísalas y vuelve a intentarlo.')

        elif enviado == 'material' and puede_apuntar_material:
            pestana = 'apuntar'
            formulario = ConsumoForm(request.POST, **opciones)
            if formulario.is_valid():
                consumo = formulario.save(commit=False)
                consumo.proyecto = proyecto
                consumo.trabajador = request.user
                # El precio se congela: si mañana cambia el catálogo, este apunte no cambia
                consumo.precio_unitario = consumo.material.precio
                consumo.save()
                messages.success(request, f'Apuntado: {consumo.cantidad_texto()} de {consumo.material.nombre}.')
                # Vuelve con la misma familia y tipo abiertos, para seguir apuntando de ellos
                return redirect(url_con_filtros(proyecto.pk, filtros, '#apuntar'))

        elif enviado == 'material':
            # Un operario no puede apuntar material aunque envíe el formulario a mano
            messages.error(request, 'El material lo apunta Oficina. Tú puedes apuntar horas, notas y albaranes.')
            return redirect('detalle_proyecto', pk=proyecto.pk)

    consumos = proyecto.consumos.select_related('material', 'trabajador', 'campo').order_by('-fecha', '-id')
    # Total de horas: suma de las cantidades de los apuntes cuya unidad es Hora
    horas = consumos.filter(material__unidad='H').aggregate(Sum('cantidad'))['cantidad__sum'] or 0

    # Apartado al que pertenece el proyecto, para el botón de volver y el menú
    slug_volver = slug_del_tipo(proyecto)

    contexto = {
        'proyecto': proyecto,
        'consumos': consumos,
        'horas': horas,
        'horas_texto': horas_texto(horas),
        'es_oficina': es_oficina,
        'puede_apuntar': puede_apuntar,
        'puede_apuntar_material': puede_apuntar_material,
        'formulario': formulario,
        'formulario_horas': formulario_horas,
        'formulario_nota': formulario_nota,
        'formulario_albaran': formulario_albaran,
        'formulario_cita': formulario_cita,
        'pestana': pestana,
        'notas': proyecto.notas.select_related('autor'),
        'albaranes': proyecto.albaranes.select_related('subido_por'),
        # Citas: primero las que quedan; luego las pasadas, de la más reciente a la más antigua
        'citas_proximas': proyecto.citas.filter(fecha__gte=date.today()),
        'citas_pasadas': proyecto.citas.filter(fecha__lt=date.today()).order_by('-fecha', '-hora'),
        'slug_volver': slug_volver,
        'nav_tipos': datos_menu(),
        'seccion': slug_volver or 'urgencias',
    }
    contexto.update(filtros)
    # El coste solo lo ve Oficina (los operarios no ven precios)
    if es_oficina:
        coste_total = 0
        for consumo in consumos:
            coste_total += consumo.total()
        contexto['coste_total'] = coste_total
    return render(request, 'gestion/detalle_proyecto.html', contexto)

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


# ---------------------------------------------------------------------------
# Editar, eliminar y repetir apuntes. El operario solo los suyos de horas; Oficina, todos.
# ---------------------------------------------------------------------------
def puede_tocar_apunte(usuario, consumo):
    if consumo.proyecto.estado == 'TER':
        return False
    if usuario.has_perm('gestion.change_proyecto'):
        return True
    return consumo.trabajador == usuario and consumo.material.unidad == 'H'

@permission_required('gestion.change_consumo')
def consumo_editar(request, pk):
    consumo = get_object_or_404(Consumo.objects.select_related('proyecto', 'material'), pk=pk)
    if not puede_tocar_apunte(request.user, consumo):
        messages.error(request, 'Solo puedes cambiar tus apuntes de horas, y en proyectos que sigan en proceso.')
        return redirect('detalle_proyecto', pk=consumo.proyecto.pk)

    material_antes = consumo.material
    campo_antes = consumo.campo
    # Un apunte de horas se edita con el selector de horas; uno de material, con la lista
    es_horas = material_antes.unidad == 'H'
    # Un oficial o un peón no cambia el puesto del apunte (solo campo, tiempo y fecha)
    puesto_fijo = material_antes if es_horas and request.user.es_operario() else None
    # Por defecto se abre la familia del material que ya tiene el apunte
    filtros = filtros_material(request, consumo.material.categoria_id)
    opciones = {'categoria': filtros['categoria_actual'], 'tipo': filtros['tipo_actual'], 'busqueda': filtros['busqueda_material']}

    if request.method == 'POST':
        if es_horas:
            formulario = HorasForm(request.POST, instance=consumo, puesto_fijo=puesto_fijo)
        else:
            formulario = ConsumoForm(request.POST, instance=consumo, **opciones)
        if formulario.is_valid():
            consumo = formulario.save(commit=False)
            # Si cambia el material (o en las horas el puesto o el campo) se toma el precio de hoy;
            # si no, se mantiene el que se guardó al apuntar
            if es_horas and (consumo.material != material_antes or consumo.campo != campo_antes):
                consumo.precio_unitario = precio_hora(consumo.material, consumo.campo)
            elif consumo.material != material_antes:
                consumo.precio_unitario = consumo.material.precio
            consumo.save()
            messages.success(request, f'Apunte de {consumo.descripcion()} actualizado.')
            return redirect('detalle_proyecto', pk=consumo.proyecto.pk)
    else:
        if es_horas:
            formulario = HorasForm(instance=consumo, puesto_fijo=puesto_fijo)
        else:
            formulario = ConsumoForm(instance=consumo, **opciones)

    slug = slug_del_tipo(consumo.proyecto)
    contexto = {
        'formulario': formulario,
        'es_horas': es_horas,
        'consumo': consumo,
        'proyecto': consumo.proyecto,
        'nav_tipos': datos_menu(),
        'seccion': slug or 'urgencias',
    }
    contexto.update(filtros)
    return render(request, 'gestion/consumo_form.html', contexto)

@permission_required('gestion.delete_consumo')
def consumo_eliminar(request, pk):
    consumo = get_object_or_404(Consumo.objects.select_related('proyecto', 'material'), pk=pk)
    if request.method == 'POST':
        if puede_tocar_apunte(request.user, consumo):
            nombre = consumo.descripcion()
            consumo.delete()
            messages.success(request, f'Apunte de {nombre} eliminado.')
        else:
            messages.error(request, 'Solo puedes eliminar tus apuntes de horas, y en proyectos que sigan en proceso.')
    return redirect(reverse('detalle_proyecto', args=[consumo.proyecto.pk]) + '#apuntes')

@permission_required('gestion.add_consumo')
def consumo_repetir(request, pk):
    # Apunta otra vez lo mismo, con fecha de hoy y a nombre de quien lo pulsa
    original = get_object_or_404(Consumo.objects.select_related('proyecto', 'material'), pk=pk)
    proyecto = original.proyecto
    if request.method == 'POST':
        if proyecto.estado == 'TER':
            messages.error(request, 'Este proyecto está terminado y ya no admite apuntes.')
        elif original.material.unidad != 'H' and not request.user.has_perm('gestion.change_proyecto'):
            messages.error(request, 'El material lo apunta Oficina. Tú puedes repetir apuntes de horas.')
        else:
            # Precio de hoy, como cualquier apunte nuevo (en las horas, el del puesto + campo)
            precio = (precio_hora(original.material, original.campo) if original.material.unidad == 'H'
                      else original.material.precio)
            nuevo = Consumo.objects.create(proyecto=proyecto, material=original.material, campo=original.campo,
                                           cantidad=original.cantidad, precio_unitario=precio,
                                           trabajador=request.user, fecha=date.today())
            messages.success(request, f'Repetido: {nuevo.cantidad_texto()} de {nuevo.descripcion()}, con fecha de hoy.')
    return redirect(reverse('detalle_proyecto', args=[proyecto.pk]) + '#apuntes')


# ---------------------------------------------------------------------------
# Notas, citas y albaranes de un proyecto
# ---------------------------------------------------------------------------
@permission_required('gestion.delete_nota')
def nota_eliminar(request, pk):
    nota = get_object_or_404(Nota.objects.select_related('proyecto'), pk=pk)
    if request.method == 'POST':
        # Cada uno borra sus notas; Oficina, todas
        if nota.autor == request.user or request.user.has_perm('gestion.change_proyecto'):
            nota.delete()
            messages.success(request, 'Nota eliminada.')
        else:
            messages.error(request, 'Solo puedes eliminar tus propias notas.')
    return redirect(reverse('detalle_proyecto', args=[nota.proyecto.pk]) + '#notas')

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

@permission_required('gestion.view_albaran')
def albaran_ver(request, pk):
    # Abre el PDF o la foto en el navegador. Pasa por esta vista (y no por una URL pública de /media/)
    # para que solo lo vean usuarios con sesión iniciada
    albaran = get_object_or_404(Albaran, pk=pk)
    try:
        archivo = albaran.archivo.open('rb')
    except FileNotFoundError:
        raise Http404('El archivo de este albarán ya no está en el servidor')
    # Las fotos HEIC no se ven en el navegador: se descargan
    return FileResponse(archivo, content_type=albaran.tipo_mime(), filename=albaran.nombre_archivo(),
                        as_attachment=not albaran.se_ve_en_navegador())

@permission_required('gestion.delete_albaran')
def albaran_eliminar(request, pk):
    albaran = get_object_or_404(Albaran.objects.select_related('proyecto'), pk=pk)
    if request.method == 'POST':
        nombre = albaran.descripcion or albaran.nombre_archivo()
        # Primero el PDF del disco y después la fila de la base de datos
        albaran.archivo.delete(save=False)
        albaran.delete()
        messages.success(request, f'Albarán «{nombre}» eliminado.')
    return redirect(reverse('detalle_proyecto', args=[albaran.proyecto.pk]) + '#albaranes')

@permission_required('gestion.change_albaran')
def lista_albaranes(request):
    # Apartado Albaranes de Oficina: los proyectos que tienen albaranes, separados por tipo
    secciones = dict(TIPOS)
    secciones['urgencias'] = {'codigo': 'URG', 'titulo': 'Urgencias'}
    seccion = request.GET.get('tipo', 'obras')
    if seccion not in secciones:
        seccion = 'obras'

    # Cuántos albaranes hay en cada apartado. order_by() vacío: si no, el ordering del Meta rompe el GROUP BY
    conteo = {}
    for fila in Albaran.objects.values('proyecto__tipo').annotate(n=Count('id')).order_by():
        conteo[fila['proyecto__tipo']] = fila['n']
    pestanas = []
    for slug, datos in secciones.items():
        n = conteo.get(datos['codigo'], 0)
        # Urgencias solo sale si tiene alguno
        if slug != 'urgencias' or n or seccion == 'urgencias':
            pestanas.append({'slug': slug, 'titulo': datos['titulo'], 'n': n})

    proyectos = (Proyecto.objects.filter(tipo=secciones[seccion]['codigo'])
                 .annotate(num_albaranes=Count('albaranes'), ultimo_albaran=Max('albaranes__fecha'))
                 .filter(num_albaranes__gt=0)
                 .order_by('-ultimo_albaran'))
    busqueda = request.GET.get('q', '').strip()
    if busqueda:
        proyectos = proyectos.filter(Q(nombre__icontains=busqueda) | Q(cliente__icontains=busqueda))

    hoy = date.today()
    return render(request, 'gestion/albaranes.html', {
        'proyectos': proyectos,
        'pestanas': pestanas,
        'tipo_actual': seccion,
        'titulo_tipo': secciones[seccion]['titulo'],
        'busqueda': busqueda,
        'total_albaranes': sum(conteo.values()),
        'albaranes_mes': Albaran.objects.filter(fecha__year=hoy.year, fecha__month=hoy.month).count(),
        'nav_tipos': datos_menu(),
        'seccion': 'albaranes',
    })


# ---------------------------------------------------------------------------
# Catálogo de materiales (Oficina): listado con buscador, filtros y orden, y CRUD
# ---------------------------------------------------------------------------
ORDEN_MATERIALES = {
    'familia': ('categoria__orden', 'tipo__nombre', 'nombre'),
    'nombre': ('nombre',),
    'precio': ('precio', 'nombre'),
    '-precio': ('-precio', 'nombre'),
}
BOTONES_CLASE = [('PRI', 'Material principal'), ('ACC', 'Accesorios'), ('SOP', 'Soportes'), ('sin', 'Sin clase')]

def url_cambiando(request, **cambios):
    # La URL actual (?categoria=...&q=...) cambiando solo algunos parámetros; los vacíos se quitan
    parametros = request.GET.dict()
    parametros.update(cambios)
    parametros = {clave: valor for clave, valor in parametros.items() if valor}
    return '?' + urlencode(parametros)

@permission_required('gestion.change_material')
def lista_materiales(request):
    materiales = Material.objects.select_related('categoria', 'tipo')

    filtros = filtros_material(request)
    if filtros['categoria_actual']:
        materiales = materiales.filter(categoria=filtros['categoria_actual'])
        if filtros['tipo_actual']:
            materiales = materiales.filter(tipo=filtros['tipo_actual'])

    busqueda = request.GET.get('q', '').strip()
    if busqueda:
        materiales = buscar_materiales(materiales, busqueda)

    # Cuántos hay de cada clase con los filtros de arriba, para los botones de clase
    conteo = {}
    for fila in materiales.values('clase').annotate(n=Count('id')).order_by():
        conteo[fila['clase'] or 'sin'] = fila['n']

    clase = request.GET.get('clase', '')
    if clase == 'sin':
        materiales = materiales.filter(clase='')
    elif clase in dict(Material.CLASES):
        materiales = materiales.filter(clase=clase)
    else:
        clase = ''

    botones_clase = [{'texto': 'Todas', 'n': sum(conteo.values()), 'url': url_cambiando(request, clase=''), 'activa': not clase}]
    for codigo, texto in BOTONES_CLASE:
        # «Sin clase» solo sale si hay alguno (mano de obra y servicios)
        if codigo != 'sin' or conteo.get('sin'):
            botones_clase.append({'codigo': codigo, 'texto': texto, 'n': conteo.get(codigo, 0),
                                  'url': url_cambiando(request, clase=codigo), 'activa': clase == codigo})

    orden = request.GET.get('orden', 'familia')
    if orden not in ORDEN_MATERIALES:
        orden = 'familia'
    materiales = materiales.order_by(*ORDEN_MATERIALES[orden])

    contexto = {
        'materiales': materiales,
        'busqueda': busqueda,
        'clase_actual': clase,
        'botones_clase': botones_clase,
        'orden_actual': orden,
        # Cabeceras de la tabla que ordenan. Precio: si ya está de menor a mayor, el siguiente clic lo invierte
        'url_orden_nombre': url_cambiando(request, orden='nombre'),
        'url_orden_familia': url_cambiando(request, orden=''),
        'url_orden_precio': url_cambiando(request, orden='-precio' if orden == 'precio' else 'precio'),
        'nav_tipos': datos_menu(),
        'seccion': 'materiales',
    }
    contexto.update(filtros)
    return render(request, 'gestion/lista_materiales.html', contexto)

@permission_required('gestion.add_material')
def material_crear(request):
    if request.method == 'POST':
        formulario = MaterialForm(request.POST)
        if formulario.is_valid():
            material = formulario.save()
            messages.success(request, f'Material «{material.nombre}» creado en {material.categoria.nombre}.')
            # «Crear y añadir otro»: vuelve al formulario con la misma familia y tipo
            if 'otro' in request.POST:
                return redirect(reverse('material_crear') + '?' + urlencode({'categoria': material.categoria_id, 'tipo': material.tipo_id or ''}))
            return redirect(reverse('lista_materiales') + f'?categoria={material.categoria_id}')
    else:
        # Si se entra desde una familia filtrada, el formulario ya viene con ella marcada
        formulario = MaterialForm(initial={'categoria': request.GET.get('categoria', 'OTR'), 'tipo': request.GET.get('tipo') or None})

    return render(request, 'gestion/material_form.html', {
        'formulario': formulario,
        'titulo': 'Nuevo material',
        'proveedores': proveedores_existentes(),
        'nav_tipos': datos_menu(),
        'seccion': 'materiales',
    })

@permission_required('gestion.change_material')
def material_editar(request, pk):
    material = get_object_or_404(Material, pk=pk)
    if request.method == 'POST':
        formulario = MaterialForm(request.POST, instance=material)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, f'Material «{material.nombre}» actualizado.')
            return redirect(reverse('lista_materiales') + f'?categoria={material.categoria_id}')
    else:
        formulario = MaterialForm(instance=material)

    return render(request, 'gestion/material_form.html', {
        'formulario': formulario,
        'material': material,
        'titulo': f'Editar «{material.nombre}»',
        'proveedores': proveedores_existentes(),
        'nav_tipos': datos_menu(),
        'seccion': 'materiales',
    })

@permission_required('gestion.delete_material')
def material_eliminar(request, pk):
    material = get_object_or_404(Material, pk=pk)
    if request.method == 'POST':
        # Un material con apuntes no se puede borrar (on_delete=PROTECT en Consumo)
        num_apuntes = material.consumos.count()
        if num_apuntes:
            messages.error(request, f'«{material.nombre}» no se puede eliminar porque se ha usado en {num_apuntes} apuntes. Puedes cambiarle el nombre o el precio.')
        else:
            material.delete()
            messages.success(request, f'Material «{material.nombre}» eliminado.')
    return redirect(reverse('lista_materiales') + f'?categoria={material.categoria_id}')


# ---------------------------------------------------------------------------
# Familias y tipos del catálogo (Oficina)
# ---------------------------------------------------------------------------
def codigo_categoria(nombre):
    # Código de 3 letras libre para una familia nueva: «Electricidad» -> ELE; si ya existe, ELC, EL2...
    letras = ''.join(c for c in sin_tildes(nombre).upper() if c.isalpha()) or 'FAM'
    candidatos = [letras[:3]]
    for i in range(1, len(letras) - 1):
        candidatos.append(letras[0] + letras[i:i + 2])
    for numero in range(2, 100):
        candidatos.append(letras[:2] + str(numero))
    for codigo in candidatos:
        if len(codigo) == 3 and not Categoria.objects.filter(pk=codigo).exists():
            return codigo
    return None

@permission_required('gestion.change_categoria')
def lista_categorias(request):
    # Crear una familia desde el formulario de la misma página
    if request.method == 'POST':
        formulario = CategoriaForm(request.POST)
        if formulario.is_valid():
            categoria = formulario.save(commit=False)
            categoria.codigo = codigo_categoria(categoria.nombre)
            if categoria.codigo is None:
                formulario.add_error('nombre', 'No se ha podido crear un código para esta familia. Prueba con otro nombre.')
            else:
                categoria.save()
                messages.success(request, f'Familia «{categoria.nombre}» creada.')
                return redirect('lista_categorias')
    else:
        formulario = CategoriaForm(initial={'orden': 85})

    # order_by explícito: con annotate (GROUP BY) Django no aplica el ordering del Meta
    categorias = Categoria.objects.annotate(num_materiales=Count('materiales', distinct=True),
                                            num_tipos=Count('tipos', distinct=True)).order_by('orden', 'nombre')
    return render(request, 'gestion/categorias.html', {
        'categorias': categorias,
        'formulario': formulario,
        'nav_tipos': datos_menu(),
        'seccion': 'materiales',
    })

@permission_required('gestion.change_categoria')
def categoria_editar(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        formulario = CategoriaForm(request.POST, instance=categoria)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, f'Familia «{categoria.nombre}» actualizada.')
            return redirect('lista_categorias')
    else:
        formulario = CategoriaForm(instance=categoria)
    return render(request, 'gestion/catalogo_form.html', {
        'formulario': formulario,
        'titulo': f'Editar la familia «{categoria.nombre}»',
        'url_lista': reverse('lista_categorias'),
        'texto_lista': 'Familias',
        'nav_tipos': datos_menu(),
        'seccion': 'materiales',
    })

@permission_required('gestion.delete_categoria')
def categoria_eliminar(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        # PROTECT: no se puede borrar una familia que aún tiene materiales o tipos
        if categoria.materiales.exists() or categoria.tipos.exists():
            messages.error(request, f'«{categoria.nombre}» no se puede eliminar porque tiene materiales o tipos. Pásalos antes a otra familia.')
        else:
            categoria.delete()
            messages.success(request, f'Familia «{categoria.nombre}» eliminada.')
    return redirect('lista_categorias')

@permission_required('gestion.change_tipo')
def lista_tipos(request):
    # Crear un tipo desde el formulario de la misma página
    if request.method == 'POST':
        formulario = TipoForm(request.POST)
        if formulario.is_valid():
            tipo = formulario.save()
            messages.success(request, f'Tipo «{tipo.nombre}» creado en {tipo.categoria.nombre}.')
            return redirect(reverse('lista_tipos') + f'?categoria={tipo.categoria_id}')
    else:
        formulario = TipoForm(initial={'categoria': request.GET.get('categoria') or None})

    tipos = Tipo.objects.select_related('categoria').annotate(num_materiales=Count('materiales')).order_by('categoria__orden', 'nombre')
    categoria = request.GET.get('categoria', '')
    if categoria:
        tipos = tipos.filter(categoria=categoria)
    return render(request, 'gestion/tipos.html', {
        'tipos': tipos,
        'formulario': formulario,
        'categorias': Categoria.objects.values_list('codigo', 'nombre'),
        'categoria_actual': categoria,
        'nav_tipos': datos_menu(),
        'seccion': 'materiales',
    })

@permission_required('gestion.change_tipo')
def tipo_editar(request, pk):
    tipo = get_object_or_404(Tipo, pk=pk)
    if request.method == 'POST':
        formulario = TipoForm(request.POST, instance=tipo)
        if formulario.is_valid():
            tipo = formulario.save()
            # Si el tipo cambia de familia, sus materiales cambian con él (update: una sola consulta)
            tipo.materiales.exclude(categoria=tipo.categoria).update(categoria=tipo.categoria)
            messages.success(request, f'Tipo «{tipo.nombre}» actualizado.')
            return redirect(reverse('lista_tipos') + f'?categoria={tipo.categoria_id}')
    else:
        formulario = TipoForm(instance=tipo)
    return render(request, 'gestion/catalogo_form.html', {
        'formulario': formulario,
        'titulo': f'Editar el tipo «{tipo.nombre}»',
        'url_lista': reverse('lista_tipos'),
        'texto_lista': 'Tipos',
        'ayuda': 'Si cambias la familia, todos los materiales de este tipo pasan a la nueva.',
        'nav_tipos': datos_menu(),
        'seccion': 'materiales',
    })

@permission_required('gestion.delete_tipo')
def tipo_eliminar(request, pk):
    tipo = get_object_or_404(Tipo, pk=pk)
    if request.method == 'POST':
        # SET_NULL: sus materiales no se borran, se quedan sin tipo
        num = tipo.materiales.count()
        tipo.delete()
        if num:
            messages.success(request, f'Tipo «{tipo.nombre}» eliminado. {num} materiales se han quedado sin tipo.')
        else:
            messages.success(request, f'Tipo «{tipo.nombre}» eliminado.')
    return redirect('lista_tipos')


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
            if rol in Usuario.ROLES_OPERARIO:
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
            messages.success(request, f'Bienvenido, {user.first_name}. Tu cuenta de {user.get_rol_display().lower()} ya está creada.')
            return redirect('index')
    else:
        formulario = RegistroForm()

    return render(request, 'registration/signup.html', {'formulario': formulario})


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

    # Qué se ve: todo, solo Outlook o solo las citas de los proyectos
    ver = request.GET.get('ver', 'todo')
    if ver not in ('todo', 'outlook', 'citas'):
        ver = 'todo'

    por_dia = {}
    for numero in range(DIAS_CALENDARIO):
        por_dia[desde + timedelta(days=numero)] = []

    error = ''
    if ver != 'citas':
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

    if ver != 'outlook':
        for cita in Cita.objects.filter(fecha__range=(desde, hasta)).select_related('proyecto'):
            por_dia[cita.fecha].append({
                'fuente': 'cita',
                'titulo': cita.motivo or 'Cita',
                'proyecto': cita.proyecto,
                'inicio': cita.hora,
                'orden': cita.hora.strftime('%H:%M') if cita.hora else '',
            })

    # Días con algo (y hoy siempre); dentro de cada día, primero lo de todo el día y luego por hora
    dias = []
    for dia, elementos in por_dia.items():
        if elementos or dia == hoy:
            elementos.sort(key=lambda elemento: elemento['orden'])
            dias.append({'fecha': dia, 'elementos': elementos, 'es_hoy': dia == hoy})

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
# Empleados (Oficina): Oficina da de alta, edita y da de baja a oficiales y peones,
# y consulta quién trabaja en la oficina
# ---------------------------------------------------------------------------
ROLES_EN_URL = {'oficial': Usuario.OFICIAL, 'peon': Usuario.PEON}


@permission_required('gestion.view_usuario')
def lista_empleados(request):
    empleados = Usuario.objects.filter(rol__in=Usuario.ROLES_OPERARIO).annotate(
        num_apuntes=Count('consumos'),
        horas=Sum('consumos__cantidad', filter=Q(consumos__material__unidad='H')),
        ultimo_apunte=Max('consumos__fecha'),
    )
    # Cuántos hay de cada rol, para los botones de arriba
    total = empleados.count()
    por_rol = {codigo: empleados.filter(rol=valor).count() for codigo, valor in ROLES_EN_URL.items()}

    rol_actual = request.GET.get('rol', '')
    if rol_actual in ROLES_EN_URL:
        empleados = empleados.filter(rol=ROLES_EN_URL[rol_actual])
    else:
        rol_actual = ''
    busqueda = request.GET.get('q', '').strip()
    if busqueda:
        empleados = empleados.filter(Q(first_name__icontains=busqueda) | Q(last_name__icontains=busqueda)
                                     | Q(username__icontains=busqueda) | Q(email__icontains=busqueda))

    botones = [{'texto': 'Todos', 'codigo': '', 'n': total}]
    botones += [{'texto': 'Oficiales', 'codigo': 'oficial', 'n': por_rol['oficial']},
                {'texto': 'Peones', 'codigo': 'peon', 'n': por_rol['peon']}]
    for boton in botones:
        parametros = {'rol': boton['codigo']} if boton['codigo'] else {}
        if busqueda:
            parametros['q'] = busqueda
        boton['url'] = '?' + urlencode(parametros) if parametros else '?'
        boton['activo'] = boton['codigo'] == rol_actual

    return render(request, 'gestion/empleados.html', {
        'empleados': empleados.order_by('-is_active', 'first_name', 'last_name'),
        'botones_rol': botones,
        'rol_actual': rol_actual,
        'busqueda': busqueda,
        'vista': 'obra',
        'seccion': 'empleados',
        'nav_tipos': datos_menu(),
    })


@permission_required('gestion.view_usuario')
def empleados_oficina(request):
    return render(request, 'gestion/empleados.html', {
        'empleados': Usuario.objects.filter(rol=Usuario.OFICINA).order_by('-is_active', 'first_name', 'last_name'),
        'vista': 'oficina',
        'seccion': 'empleados',
        'nav_tipos': datos_menu(),
    })


def poner_en_grupo_operarios(empleado):
    """Oficiales y peones tienen los permisos del grupo «Operarios» y su ficha de Operario."""
    Operario.objects.get_or_create(usuario=empleado)
    grupo = Group.objects.filter(name='Operarios').first()
    if grupo:
        grupo.user_set.add(empleado)


@permission_required('gestion.add_usuario')
def empleado_crear(request):
    if request.method == 'POST':
        formulario = EmpleadoForm(request.POST)
        if formulario.is_valid():
            empleado = formulario.save()
            poner_en_grupo_operarios(empleado)
            messages.success(request, f'{empleado.get_full_name()} ya puede entrar como {empleado.get_rol_display().lower()} con el usuario «{empleado.username}».')
            if request.POST.get('otro'):
                return redirect('empleado_crear')
            return redirect('lista_empleados')
    else:
        # Si se viene desde «Peones», el rol ya sale marcado
        formulario = EmpleadoForm(initial={'rol': ROLES_EN_URL.get(request.GET.get('rol'), Usuario.OFICIAL)})
    return render(request, 'gestion/empleado_form.html', {
        'formulario': formulario,
        'titulo': 'Nuevo empleado',
        'seccion': 'empleados',
        'nav_tipos': datos_menu(),
    })


@permission_required('gestion.change_usuario')
def empleado_editar(request, pk):
    # Desde aquí solo se gestionan oficiales y peones (Oficina y el administrador, desde /admin)
    empleado = get_object_or_404(Usuario, pk=pk, rol__in=Usuario.ROLES_OPERARIO)
    if request.method == 'POST':
        formulario = EmpleadoForm(request.POST, instance=empleado)
        if formulario.is_valid():
            empleado = formulario.save()
            poner_en_grupo_operarios(empleado)
            messages.success(request, f'Datos de {empleado.get_full_name()} guardados.')
            return redirect('lista_empleados')
    else:
        formulario = EmpleadoForm(instance=empleado)
    return render(request, 'gestion/empleado_form.html', {
        'formulario': formulario,
        'empleado': empleado,
        'num_apuntes': empleado.consumos.count(),
        'titulo': f'Editar a {empleado.get_full_name() or empleado.username}',
        'seccion': 'empleados',
        'nav_tipos': datos_menu(),
    })


@permission_required('gestion.delete_usuario')
def empleado_eliminar(request, pk):
    empleado = get_object_or_404(Usuario, pk=pk, rol__in=Usuario.ROLES_OPERARIO)
    if request.method == 'POST':
        nombre = empleado.get_full_name() or empleado.username
        try:
            empleado.delete()
            messages.success(request, f'{nombre} eliminado.')
        except ProtectedError:
            # Tiene apuntes o albaranes (on_delete=PROTECT): borrarlo haría perderlos
            messages.error(request, f'{nombre} no se puede eliminar porque tiene apuntes o albaranes. Desmarca «Puede entrar en la aplicación» para darle de baja.')
            return redirect('empleado_editar', pk=empleado.pk)
    return redirect('lista_empleados')


# ---------------------------------------------------------------------------
# Precios horas (Oficina): el precio de una hora depende del puesto (Oficial, Peón...)
# y del campo (Electricidad, Fontanería...). Aquí se crean puestos y campos y se fija
# el precio de cada combinación.
# ---------------------------------------------------------------------------
def elegido(consulta, datos, nombre):
    """Objeto elegido en la URL (?puesto=3) o en el formulario enviado; None si no llega o no existe."""
    valor = datos.get(nombre, '')
    return consulta.filter(pk=valor).first() if valor.isdigit() else None


def url_precios(puesto=None, campo=None):
    """Dirección de Precios horas con el puesto y el campo elegidos."""
    parametros = {}
    if puesto:
        parametros['puesto'] = puesto.pk
    if campo:
        parametros['campo'] = campo.pk
    url = reverse('precios_horas')
    return url + ('?' + urlencode(parametros) if parametros else '') + '#fijar'


@permission_required('gestion.change_material')
def precios_horas(request):
    puestos = Material.objects.filter(unidad='H').annotate(num_apuntes=Count('consumos')).order_by('nombre')
    campos = CampoHora.objects.annotate(num_apuntes=Count('consumos'))
    puesto = elegido(puestos, request.GET, 'puesto')
    campo = elegido(campos, request.GET, 'campo')
    tarifa = TarifaHora.objects.filter(puesto=puesto, campo=campo).first() if puesto and campo else None

    formulario_puesto = PuestoForm()
    formulario_campo = CampoHoraForm()
    formulario_tarifa = TarifaForm(initial={
        'puesto': puesto,
        'campo': campo,
        'precio': tarifa.precio if tarifa else (puesto.precio if puesto else None),
    })
    # Qué bloque abrir al volver con errores
    abierto = ''

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'puesto':
            formulario_puesto = PuestoForm(request.POST)
            if formulario_puesto.is_valid():
                # Mano de obra si existe esa familia; si no, Otros
                familia = 'MOB' if Categoria.objects.filter(pk='MOB').exists() else 'OTR'
                tipo_horas, _ = Tipo.objects.get_or_create(nombre='Horas', categoria_id=familia)
                nuevo = Material.objects.create(
                    nombre=f"Hora {formulario_puesto.cleaned_data['nombre']}",
                    categoria_id=familia,
                    tipo=tipo_horas,
                    unidad='H',
                    clase='',
                    precio=formulario_puesto.cleaned_data['precio'],
                )
                messages.success(request, f'Puesto «{nuevo.nombre_puesto()}» creado.')
                return redirect(url_precios(nuevo, campo))
            abierto = 'puesto'
        elif accion == 'campo':
            formulario_campo = CampoHoraForm(request.POST)
            if formulario_campo.is_valid():
                nuevo = formulario_campo.save()
                messages.success(request, f'Campo «{nuevo.nombre}» creado.')
                return redirect(url_precios(puesto, nuevo))
            abierto = 'campo'
        elif accion == 'tarifa':
            formulario_tarifa = TarifaForm(request.POST)
            if formulario_tarifa.is_valid():
                datos = formulario_tarifa.cleaned_data
                # update_or_create: si la combinación ya tenía precio se cambia; si no, se crea
                tarifa, creada = TarifaHora.objects.update_or_create(
                    puesto=datos['puesto'], campo=datos['campo'], defaults={'precio': datos['precio']},
                )
                accion_texto = 'fijado' if creada else 'actualizado'
                precio_texto = f'{tarifa.precio:.2f}'.replace('.', ',')
                messages.success(request, f'Precio {accion_texto}: {tarifa.puesto.nombre_puesto()} · {tarifa.campo.nombre}, {precio_texto} €/h.')
                return redirect(url_precios(tarifa.puesto, tarifa.campo))
            # Con errores se sigue mostrando la combinación que se estaba fijando
            puesto = puesto or elegido(puestos, request.POST, 'puesto')
            campo = campo or elegido(campos, request.POST, 'campo')

    tarifas = TarifaHora.objects.select_related('puesto', 'campo')
    return render(request, 'gestion/precios_horas.html', {
        'puestos': puestos,
        'campos': campos,
        'puesto_actual': puesto,
        'campo_actual': campo,
        'tarifa_actual': tarifa,
        'formulario_puesto': formulario_puesto,
        'formulario_campo': formulario_campo,
        'formulario_tarifa': formulario_tarifa,
        'abierto': abierto,
        'tarifas': tarifas,
        'combinaciones_sin_precio': puestos.count() * campos.count() - tarifas.count(),
        'seccion': 'precios_horas',
        'nav_tipos': datos_menu(),
    })


@permission_required('gestion.change_material')
def puesto_eliminar(request, pk):
    puesto = get_object_or_404(Material, pk=pk, unidad='H')
    if request.method == 'POST':
        # Un puesto con horas apuntadas no se borra: se perderían esas horas (on_delete=PROTECT en Consumo)
        num_apuntes = puesto.consumos.count()
        if num_apuntes:
            messages.error(request, f'«{puesto.nombre_puesto()}» no se puede eliminar porque tiene {num_apuntes} apuntes de horas.')
        else:
            nombre = puesto.nombre_puesto()
            puesto.delete()   # sus precios por campo se borran con él (CASCADE)
            messages.success(request, f'Puesto «{nombre}» eliminado.')
    return redirect(reverse('precios_horas') + '#fijar')


@permission_required('gestion.change_material')
def campo_hora_eliminar(request, pk):
    campo = get_object_or_404(CampoHora, pk=pk)
    if request.method == 'POST':
        num_apuntes = campo.consumos.count()
        if num_apuntes:
            messages.error(request, f'«{campo.nombre}» no se puede eliminar porque tiene {num_apuntes} apuntes de horas.')
        else:
            nombre = campo.nombre
            campo.delete()
            messages.success(request, f'Campo «{nombre}» eliminado.')
    return redirect(reverse('precios_horas') + '#fijar')


@permission_required('gestion.change_material')
def tarifa_eliminar(request, pk):
    tarifa = get_object_or_404(TarifaHora.objects.select_related('puesto', 'campo'), pk=pk)
    if request.method == 'POST':
        texto = f'{tarifa.puesto.nombre_puesto()} · {tarifa.campo.nombre}'
        tarifa.delete()
        messages.success(request, f'Precio de {texto} quitado. Esas horas usarán el precio base del puesto.')
    return redirect(reverse('precios_horas') + '#precios')


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
