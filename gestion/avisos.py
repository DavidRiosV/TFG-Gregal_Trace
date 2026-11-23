"""
Avisos por WhatsApp a los empleados (preparado para más adelante).

Cuando Oficina agenda un trabajo a un empleado se llama a avisar_asignacion(). Si en el .env
hay WHATSAPP_WEBHOOK_URL, se envían los datos del trabajo a esa dirección (por ejemplo, un flujo
de n8n con un webhook que manda el mensaje de WhatsApp). Si no hay dirección o el empleado no
tiene móvil, no se hace nada: la agenda funciona igual.
"""
import json
import urllib.request

from django.conf import settings
from django.utils import timezone


def texto_aviso(asignacion):
    """Mensaje que recibe el empleado: «Hola Joan, el jueves 26/11 (mañana) vas a OBR26026 ...»."""
    proyecto = asignacion.proyecto
    texto = (f'Hola {asignacion.empleado.first_name}, el {asignacion.fecha:%d/%m} '
             f'({asignacion.get_franja_display().lower()}) vas a {proyecto.nombre}')
    if proyecto.cliente:
        texto += f' · {proyecto.cliente}'
    if asignacion.nota:
        texto += f'. Nota: {asignacion.nota}'
    return texto + '.'


def avisar_asignacion(asignacion):
    """Envía el aviso. Devuelve True si se envió y guarda cuándo; False si no se pudo o no está configurado."""
    url = getattr(settings, 'WHATSAPP_WEBHOOK_URL', '')
    telefono = asignacion.empleado.telefono
    if not url or not telefono:
        return False
    datos = {
        'telefono': telefono,
        'mensaje': texto_aviso(asignacion),
        'empleado': asignacion.empleado.get_full_name() or asignacion.empleado.username,
        'trabajo': asignacion.proyecto.nombre,
        'fecha': asignacion.fecha.isoformat(),
        'franja': asignacion.get_franja_display(),
    }
    peticion = urllib.request.Request(url, data=json.dumps(datos).encode('utf-8'),
                                      headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(peticion, timeout=5):
            pass
    except OSError:
        # Sin conexión o el webhook falla: la asignación se guarda igual, solo que sin aviso
        return False
    asignacion.avisada = timezone.now()
    asignacion.save(update_fields=['avisada'])
    return True
