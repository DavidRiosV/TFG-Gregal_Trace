"""Ficha del proyecto y apuntes de horas y material: apuntar, editar, borrar y repetir; notas."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..forms import AlbaranForm, CitaForm, ConsumoForm, HorasForm, NotaForm
from ..models import Consumo, horas_texto, Material, Nota, precio_hora, Proyecto, Usuario
from .comun import datos_menu, filtros_material, slug_del_tipo, url_con_filtros


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
