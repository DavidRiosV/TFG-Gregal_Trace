"""Empleados (Oficina) y registro de usuarios nuevos."""
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import Group
from django.db.models import Count, Max, ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..avisos import avisar_asignacion
from ..forms import AsignacionForm, EmpleadoForm, RegistroForm
from ..models import Asignacion, Oficina, Operario, Usuario
from .comun import datos_menu


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

    # Dónde trabaja hoy cada uno (agenda de empleados)
    hoy = {}
    for asignacion in Asignacion.objects.filter(fecha=date.today()).select_related('proyecto'):
        hoy.setdefault(asignacion.empleado_id, []).append(asignacion)
    empleados = list(empleados.order_by('-is_active', 'first_name', 'last_name'))
    for empleado in empleados:
        empleado.hoy = hoy.get(empleado.pk, [])

    return render(request, 'gestion/empleados.html', {
        'empleados': empleados,
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
# Agenda de empleados (Oficina): a qué trabajo abierto va cada oficial o peón cada día
# ---------------------------------------------------------------------------
def lunes_de(fecha):
    return fecha - timedelta(days=fecha.weekday())


@permission_required('gestion.add_asignacion')
def empleado_agenda(request, pk):
    empleado = get_object_or_404(Usuario, pk=pk, rol__in=Usuario.ROLES_OPERARIO)

    # Semana que se ve: la de ?semana=2026-11-23 o la actual. Siempre empieza en lunes
    try:
        lunes = lunes_de(datetime.strptime(request.GET.get('semana', ''), '%Y-%m-%d').date())
    except ValueError:
        lunes = lunes_de(date.today())

    if request.method == 'POST':
        formulario = AsignacionForm(request.POST, empleado=empleado)
        if formulario.is_valid():
            asignacion = formulario.save(commit=False)
            asignacion.empleado = empleado
            asignacion.creada_por = request.user
            asignacion.save()
            texto = f'{empleado.first_name} va a {asignacion.proyecto.nombre} el {asignacion.fecha:%d/%m} ({asignacion.get_franja_display().lower()}).'
            # Aviso por WhatsApp: solo si está configurado (WHATSAPP_WEBHOOK_URL) y tiene móvil
            if avisar_asignacion(asignacion):
                texto += ' Se le ha avisado por WhatsApp.'
            messages.success(request, texto)
            # Vuelve a la semana del día agendado
            return redirect(f"{request.path}?semana={lunes_de(asignacion.fecha):%Y-%m-%d}")
    else:
        formulario = AsignacionForm(empleado=empleado, initial={'fecha': date.today(), 'franja': 'DIA'})

    # Los 7 días de la semana con lo que tiene cada uno
    asignaciones = (Asignacion.objects.filter(empleado=empleado, fecha__range=(lunes, lunes + timedelta(days=6)))
                    .select_related('proyecto'))
    dias = []
    for numero in range(7):
        dia = lunes + timedelta(days=numero)
        dias.append({'fecha': dia, 'asignaciones': [a for a in asignaciones if a.fecha == dia]})

    return render(request, 'gestion/empleado_agenda.html', {
        'empleado': empleado,
        'formulario': formulario,
        'dias': dias,
        'lunes': lunes,
        'domingo': lunes + timedelta(days=6),
        'hoy': date.today(),
        'semana_anterior': f'{lunes - timedelta(days=7):%Y-%m-%d}',
        'semana_siguiente': f'{lunes + timedelta(days=7):%Y-%m-%d}',
        'es_esta_semana': lunes == lunes_de(date.today()),
        'seccion': 'empleados',
        'nav_tipos': datos_menu(),
    })


@permission_required('gestion.delete_asignacion')
def asignacion_eliminar(request, pk):
    asignacion = get_object_or_404(Asignacion.objects.select_related('empleado', 'proyecto'), pk=pk)
    volver = f"{reverse('empleado_agenda', args=[asignacion.empleado_id])}?semana={lunes_de(asignacion.fecha):%Y-%m-%d}"
    if request.method == 'POST':
        asignacion.delete()
        messages.success(request, f'Quitado: {asignacion.proyecto.nombre} el {asignacion.fecha:%d/%m}.')
    return redirect(volver)
