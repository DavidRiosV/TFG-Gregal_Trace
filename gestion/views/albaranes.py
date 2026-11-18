"""Albaranes y fotos de la obra: verlos, borrarlos y el listado de Oficina."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db.models import Count, Max, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..models import Albaran, Proyecto
from .comun import datos_menu, TIPOS


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
