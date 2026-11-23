"""Vehículos (Gestión): furgonetas y coches con su kilometraje, revisiones (taller e ITV) y anotaciones.
Oficina lo gestiona todo; el trabajador responsable ve su vehículo, sus revisiones, apunta los
kilómetros y escribe anotaciones."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..forms import KilometrajeForm, NotaVehiculoForm, RevisionVehiculoForm, VehiculoForm
from ..models import Kilometraje, NotaVehiculo, RevisionVehiculo, Vehiculo
from .comun import datos_menu

NOMBRES_MES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto',
               'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def gestiona_vehiculos(usuario):
    """Oficina: ve y cambia todos los vehículos."""
    return usuario.has_perm('gestion.change_vehiculo')


def vehiculo_permitido(request, pk):
    """El vehículo, si el usuario puede verlo: Oficina, cualquiera; un trabajador, solo del que es responsable.
    Si no, 404 (como si no existiera)."""
    vehiculo = get_object_or_404(Vehiculo.objects.select_related('responsable'), pk=pk)
    if not gestiona_vehiculos(request.user) and vehiculo.responsable_id != request.user.pk:
        raise Http404('Vehículo no encontrado')
    return vehiculo


def km_por_meses(lecturas, meses=6):
    """Kilómetros recorridos en cada uno de los últimos meses: la última lectura del mes menos la
    última de antes (o la primera del mes si no hay ninguna anterior).
    None si no se puede calcular: sin lecturas ese mes, o con una sola y ninguna anterior con la que restar
    (en ese caso, primera=True: es la primera lectura del vehículo)."""
    lecturas = sorted(lecturas, key=lambda l: (l.fecha, l.km))
    hoy = date.today()
    resultado = []
    for atras in range(meses - 1, -1, -1):
        anio, mes = hoy.year, hoy.month - atras
        while mes < 1:
            mes += 12
            anio -= 1
        inicio = date(anio, mes, 1)
        fin = date(anio + (mes == 12), mes % 12 + 1, 1)    # primer día del mes siguiente
        del_mes = [l for l in lecturas if inicio <= l.fecha < fin]
        antes = [l for l in lecturas if l.fecha < inicio]
        recorrido = None
        primera = False
        if del_mes and antes:
            recorrido = del_mes[-1].km - antes[-1].km
        elif len(del_mes) > 1:
            recorrido = del_mes[-1].km - del_mes[0].km
        elif del_mes:
            # Una sola lectura y ninguna antes: aún no hay con qué comparar (no son 0 km)
            primera = True
        resultado.append({'mes': f'{NOMBRES_MES[mes - 1]} {anio}', 'km': recorrido, 'primera': primera})
    return list(reversed(resultado))


@login_required
def lista_vehiculos(request):
    if gestiona_vehiculos(request.user):
        vehiculos = Vehiculo.objects.select_related('responsable')
    else:
        # Un trabajador solo ve los suyos; si tiene uno, va directo a él
        vehiculos = Vehiculo.objects.filter(responsable=request.user, activo=True)
        if len(vehiculos) == 1:
            return redirect('detalle_vehiculo', pk=vehiculos[0].pk)
    vehiculos = list(vehiculos)
    for vehiculo in vehiculos:
        vehiculo.ultimo = vehiculo.ultimo_kilometraje()
        vehiculo.proxima = vehiculo.proxima_revision()
    return render(request, 'gestion/vehiculos.html', {
        'vehiculos': vehiculos,
        'gestiona': gestiona_vehiculos(request.user),
        'seccion': 'vehiculos',
        'nav_tipos': datos_menu(),
    })


@permission_required('gestion.add_vehiculo')
def vehiculo_crear(request):
    if request.method == 'POST':
        formulario = VehiculoForm(request.POST)
        if formulario.is_valid():
            vehiculo = formulario.save()
            if vehiculo.responsable:
                NotaVehiculo.objects.create(vehiculo=vehiculo, autor=request.user, automatica=True,
                                            texto=f'Alta del vehículo. Responsable: {nombre_de(vehiculo.responsable)}.')
            messages.success(request, f'{vehiculo.get_tipo_display()} {vehiculo.matricula} dada de alta.')
            return redirect('detalle_vehiculo', pk=vehiculo.pk)
    else:
        formulario = VehiculoForm()
    return render(request, 'gestion/vehiculo_form.html', {
        'formulario': formulario, 'titulo': 'Nuevo vehículo', 'seccion': 'vehiculos', 'nav_tipos': datos_menu(),
    })


def nombre_de(usuario):
    return (usuario.get_full_name() or usuario.username) if usuario else 'nadie'


@permission_required('gestion.change_vehiculo')
def vehiculo_editar(request, pk):
    vehiculo = get_object_or_404(Vehiculo, pk=pk)
    responsable_antes = vehiculo.responsable
    if request.method == 'POST':
        formulario = VehiculoForm(request.POST, instance=vehiculo)
        if formulario.is_valid():
            vehiculo = formulario.save()
            if vehiculo.responsable != responsable_antes:
                # Queda en el historial. Lo apuntado antes (km y anotaciones) sigue con su autor
                NotaVehiculo.objects.create(
                    vehiculo=vehiculo, autor=request.user, automatica=True,
                    texto=f'Cambio de responsable: {nombre_de(responsable_antes)} → {nombre_de(vehiculo.responsable)}.')
            messages.success(request, f'Datos de {vehiculo.matricula} guardados.')
            return redirect('detalle_vehiculo', pk=vehiculo.pk)
    else:
        formulario = VehiculoForm(instance=vehiculo)
    return render(request, 'gestion/vehiculo_form.html', {
        'formulario': formulario, 'vehiculo': vehiculo, 'titulo': f'Editar {vehiculo.matricula}',
        'seccion': 'vehiculos', 'nav_tipos': datos_menu(),
    })


@permission_required('gestion.delete_vehiculo')
def vehiculo_eliminar(request, pk):
    vehiculo = get_object_or_404(Vehiculo, pk=pk)
    if request.method == 'POST':
        vehiculo.delete()
        messages.success(request, f'Vehículo {vehiculo.matricula} eliminado con su historial.')
        return redirect('lista_vehiculos')
    return redirect('detalle_vehiculo', pk=pk)


@login_required
def detalle_vehiculo(request, pk):
    vehiculo = vehiculo_permitido(request, pk)
    gestiona = gestiona_vehiculos(request.user)

    formulario_km = KilometrajeForm(vehiculo=vehiculo, initial={'fecha': date.today()})
    formulario_revision = RevisionVehiculoForm(initial={'tipo': 'TAL'})
    formulario_nota = NotaVehiculoForm()
    pestana = 'kilometraje'

    if request.method == 'POST':
        enviado = request.POST.get('apunte')
        if enviado == 'km':
            # Kilómetros: Oficina o el responsable. Se guarda quién y a qué hora
            formulario_km = KilometrajeForm(request.POST, vehiculo=vehiculo)
            if formulario_km.is_valid():
                lectura = formulario_km.save(commit=False)
                lectura.vehiculo = vehiculo
                lectura.registrado_por = request.user
                lectura.save()
                messages.success(request, f'Apuntados {lectura.km} km el {lectura.fecha:%d/%m/%Y}.')
                return redirect(reverse('detalle_vehiculo', args=[vehiculo.pk]) + '#kilometraje')
        elif enviado == 'revision' and gestiona:
            # Revisiones (taller o ITV): solo Oficina
            pestana = 'revisiones'
            formulario_revision = RevisionVehiculoForm(request.POST)
            if formulario_revision.is_valid():
                revision = formulario_revision.save(commit=False)
                revision.vehiculo = vehiculo
                revision.creada_por = request.user
                revision.save()
                messages.success(request, f'{revision.get_tipo_display()} el {revision.fecha:%d/%m/%Y} ({revision.dias()}).')
                return redirect(reverse('detalle_vehiculo', args=[vehiculo.pk]) + '#revisiones')
        elif enviado == 'nota':
            pestana = 'anotaciones'
            formulario_nota = NotaVehiculoForm(request.POST)
            if formulario_nota.is_valid():
                nota = formulario_nota.save(commit=False)
                nota.vehiculo = vehiculo
                nota.autor = request.user
                nota.save()
                messages.success(request, 'Anotación guardada.')
                return redirect(reverse('detalle_vehiculo', args=[vehiculo.pk]) + '#anotaciones')

    # Lecturas, de la más reciente a la más antigua, con lo recorrido desde la anterior
    lecturas = list(vehiculo.kilometrajes.select_related('registrado_por'))
    for numero, lectura in enumerate(lecturas):
        anterior = lecturas[numero + 1] if numero + 1 < len(lecturas) else None
        lectura.recorrido = lectura.km - anterior.km if anterior else None

    hoy = date.today()
    return render(request, 'gestion/vehiculo.html', {
        'vehiculo': vehiculo,
        'gestiona': gestiona,
        'lecturas': lecturas,
        'ultimo': lecturas[0] if lecturas else None,
        'km_meses': km_por_meses(lecturas),
        'revisiones_proximas': vehiculo.revisiones.filter(fecha__gte=hoy),
        'revisiones_pasadas': vehiculo.revisiones.filter(fecha__lt=hoy).order_by('-fecha', '-hora'),
        'notas': vehiculo.notas.select_related('autor'),
        'formulario_km': formulario_km,
        'formulario_revision': formulario_revision,
        'formulario_nota': formulario_nota,
        'pestana': pestana,
        'seccion': 'vehiculos',
        'nav_tipos': datos_menu(),
    })


@permission_required('gestion.delete_kilometraje')
def kilometraje_eliminar(request, pk):
    lectura = get_object_or_404(Kilometraje, pk=pk)
    if request.method == 'POST':
        lectura.delete()
        messages.success(request, f'Lectura de {lectura.km} km eliminada.')
    return redirect(reverse('detalle_vehiculo', args=[lectura.vehiculo_id]) + '#kilometraje')


@permission_required('gestion.delete_revisionvehiculo')
def revision_vehiculo_eliminar(request, pk):
    revision = get_object_or_404(RevisionVehiculo, pk=pk)
    if request.method == 'POST':
        revision.delete()
        messages.success(request, f'{revision.get_tipo_display()} del {revision.fecha:%d/%m/%Y} eliminada.')
    return redirect(reverse('detalle_vehiculo', args=[revision.vehiculo_id]) + '#revisiones')


@login_required
def nota_vehiculo_eliminar(request, pk):
    nota = get_object_or_404(NotaVehiculo, pk=pk)
    # Las anotaciones pasadas no se tocan: cada uno solo puede borrar las suyas (Oficina tampoco las de
    # otros) y las automáticas del historial no se borran
    if request.method == 'POST' and nota.autor_id == request.user.pk and not nota.automatica:
        nota.delete()
        messages.success(request, 'Anotación eliminada.')
    return redirect(reverse('detalle_vehiculo', args=[nota.vehiculo_id]) + '#anotaciones')


@permission_required('gestion.change_kilometraje')
def kilometraje_editar(request, pk):
    lectura = get_object_or_404(Kilometraje.objects.select_related('vehiculo', 'registrado_por'), pk=pk)
    if request.method == 'POST':
        formulario = KilometrajeForm(request.POST, instance=lectura, vehiculo=lectura.vehiculo)
        if formulario.is_valid():
            # Se corrige el dato, pero se mantiene quién lo apuntó y cuándo
            formulario.save()
            messages.success(request, f'Lectura corregida: {lectura.km} km el {lectura.fecha:%d/%m/%Y}.')
            return redirect(reverse('detalle_vehiculo', args=[lectura.vehiculo_id]) + '#kilometraje')
    else:
        formulario = KilometrajeForm(instance=lectura, vehiculo=lectura.vehiculo)
    return render(request, 'gestion/vehiculo_editar_dato.html', {
        'formulario': formulario, 'vehiculo': lectura.vehiculo, 'titulo': 'Corregir kilometraje',
        'detalle': f'Apuntado por {nombre_de(lectura.registrado_por)} el {lectura.registrado:%d/%m/%Y a las %H:%M}',
        'ancla': 'kilometraje', 'seccion': 'vehiculos', 'nav_tipos': datos_menu(),
    })


@permission_required('gestion.change_revisionvehiculo')
def revision_vehiculo_editar(request, pk):
    revision = get_object_or_404(RevisionVehiculo.objects.select_related('vehiculo'), pk=pk)
    if request.method == 'POST':
        formulario = RevisionVehiculoForm(request.POST, instance=revision)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, f'{revision.get_tipo_display()} del {revision.fecha:%d/%m/%Y} guardada.')
            return redirect(reverse('detalle_vehiculo', args=[revision.vehiculo_id]) + '#revisiones')
    else:
        formulario = RevisionVehiculoForm(instance=revision)
    return render(request, 'gestion/vehiculo_editar_dato.html', {
        'formulario': formulario, 'vehiculo': revision.vehiculo, 'titulo': 'Cambiar revisión',
        'ancla': 'revisiones', 'seccion': 'vehiculos', 'nav_tipos': datos_menu(),
    })
