# Gregal Trace

Aplicación web con Django para Instalaciones Gregal: registro del material y las horas que se gastan en cada obra, intervención y mantenimiento.

Proyecto Integrado de 2.º DAW (IES Polígono Sur) · David Ríos Valencia.

## Hito 1: esqueleto del proyecto
- Modelo de datos completo (usuarios con rol, proyectos, materiales, apuntes y albaranes) con sus migraciones.
- Panel de administración con todos los modelos.
- Plantilla base con menú, cabecera y pie, adaptada a móvil.
- Inicio con las secciones Obras, Intervenciones y Mantenimientos y sus contadores.
- Listado de cada sección con buscador y filtro por estado.
- Detalle de cada proyecto en modo consulta: datos, apuntes y total de horas.

## Puesta en marcha
    python -m venv myvenv
    myvenv\Scripts\activate          (Linux: source myvenv/bin/activate)
    pip install -r requirements.txt
    python manage.py migrate
    python manage.py createsuperuser
    python manage.py runserver

Los datos reales de la empresa no se publican en el repositorio. Para probar, crea proyectos, materiales y apuntes desde el panel de administración (/admin).