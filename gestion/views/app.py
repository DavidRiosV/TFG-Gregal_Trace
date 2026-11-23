"""App instalable (PWA): el service worker y la página «Sin conexión»."""
from django.shortcuts import render


def service_worker(request):
    # Se sirve desde /sw.js (no desde /static/) para que su alcance sea toda la web
    return render(request, 'gestion/sw.js', content_type='application/javascript')


def sin_conexion(request):
    # Página independiente que el service worker guarda en el móvil para enseñarla sin cobertura
    return render(request, 'gestion/sin_conexion.html')
