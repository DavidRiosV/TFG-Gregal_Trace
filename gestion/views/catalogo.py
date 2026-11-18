"""Catálogo (Oficina): materiales, familias, tipos y precios de las horas."""
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..forms import CampoHoraForm, CategoriaForm, MaterialForm, PuestoForm, TarifaForm, TipoForm
from ..models import buscar_materiales, CampoHora, Categoria, Material, sin_tildes, TarifaHora, Tipo
from .comun import datos_menu, filtros_material, proveedores_existentes


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
