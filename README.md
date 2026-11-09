# Gregal Trace

Aplicación web con Django para **Instalaciones Gregal**. Sirve para registrar el material y las horas que se gastan en cada obra, intervención y mantenimiento, y saber así cuánto cuesta y cuánto tarda cada trabajo.

Proyecto Integrado de 2.º DAW (IES Polígono Sur) · David Ríos Valencia.

## Tecnologías

- Python 3.12 y Django 5.1
- SQLite (base de datos de desarrollo)
- HTML, CSS y JavaScript propios, sin frameworks de estilos, con diseño adaptado a móvil

## Usuarios y permisos

| Rol | Grupo | Qué puede hacer |
|---|---|---|
| Operario | `Operarios` | Ver todos los proyectos y sus apuntes, y abrir urgencias |
| Oficina | `Oficina` | Todo lo anterior, y además crear, editar, terminar y eliminar proyectos |
| Administrador | superusuario | Panel de administración de Django (`/admin/`), solo para el desarrollador |

Apuntar material y horas desde la web y gestionar el catálogo de materiales llegan en el Hito 3.

Los permisos se controlan con los grupos de Django: cada vista lleva `@permission_required` y las plantillas solo muestran los botones que el usuario puede usar (`perms`).

## Hito 1: esqueleto del proyecto

- Modelo de datos completo: usuarios con rol (`AbstractUser`), Operario y Oficina, proyectos, materiales, apuntes y albaranes, con sus migraciones.
- Panel de administración con todos los modelos (el de usuarios con `UserAdmin`, para que la contraseña se guarde cifrada).
- Plantilla base con menú lateral, cabecera, pie y barra inferior en el móvil.
- Inicio con las secciones Obras, Intervenciones y Mantenimientos y sus contadores.
- Listado de cada sección con buscador y filtro por estado (en proceso, terminados, todos).
- Detalle de cada proyecto: datos, apuntes y total de horas.

## Hito 2: usuarios, permisos, sesión y CRUD

### Registro, login y logout
- Registro de operarios (`/registrar/`) con `UserCreationForm`: crea el usuario, su `Operario` y lo mete en el grupo `Operarios`. Al terminar entra directamente, sin pasar por el login.
- Login y logout con las vistas de Django (`/accounts/`). Si alguien abre una página sin haber entrado, va al login y, al entrar, vuelve a esa página (`?next=`).

### Permisos
- **Ninguna página es accesible sin iniciar sesión.**
- Cada acción exige su permiso: los operarios solo consultan y abren urgencias; Oficina gestiona los proyectos.
- Crear proyectos pide `add_proyecto` y `change_proyecto` a la vez, para que un operario (que tiene `add_proyecto` por las urgencias) no pueda crear obras.

### Sesión
- La hora de entrada se guarda en la sesión y se muestra en el menú.
- El último proyecto abierto se guarda en la sesión y la portada ofrece «Seguir con…». Si ese proyecto se elimina, se quita de la sesión (`del request.session[...]`).

### CRUD de proyectos (Oficina)
- **Crear** obras, intervenciones y mantenimientos desde su listado. El tipo viene marcado y se guarda quién lo creó.
- **Ver** el detalle con sus datos, apuntes y horas.
- **Editar** con el mismo formulario que crear (`instance=`).
- **Eliminar** solo por POST y con confirmación.
- **Terminar o volver a poner en proceso** con un botón; pone o quita la fecha de fin.
- Validaciones del formulario (`clean()`): la fecha de fin y la de entrega no pueden ser anteriores a la de inicio; un proyecto terminado necesita fecha de fin y uno en proceso no la lleva.

### Urgencias
- Cualquier usuario abre una urgencia (un trabajo que aún no está dado de alta) e indica en qué se convertirá: obra, intervención o mantenimiento.
- Página de urgencias con el formulario y la lista de las abiertas, y tarjeta propia en la portada.
- Cuando Oficina la termina, pasa sola a su apartado, como terminada y con todos sus apuntes.

### Otras mejoras de este hito
- **Familias y tipos de material como modelos** (`Categoria` y `Tipo`), para poder crearlos y editarlos más adelante sin tocar el código. La migración conserva la familia y el tipo de los materiales que ya existían.
- **Fecha de entrega** en los proyectos. Los proyectos en proceso se ordenan por entrega y el listado avisa en ámbar si quedan 7 días o menos y en rojo si ya ha vencido.
- **Menú con una sola consulta**: los contadores se calculan agrupando (`values().annotate(Count())`) en lugar de hacer un `count()` por apartado.

## URLs

| URL | Qué hace | Quién |
|---|---|---|
| `/` | Portada con los apartados y sus contadores | Con sesión iniciada |
| `/registrar/` | Registro de operarios | Sin sesión |
| `/accounts/login/` y `/accounts/logout/` | Iniciar y cerrar sesión | Todos |
| `/proyectos/<obras\|intervenciones\|mantenimientos>/` | Listado con buscador y filtro por estado (`re_path`) | Con sesión iniciada |
| `/proyectos/<tipo>/nuevo/` | Crear proyecto | Oficina |
| `/proyecto/<id>/` | Detalle del proyecto | Con sesión iniciada |
| `/proyecto/<id>/editar/` | Editar proyecto | Oficina |
| `/proyecto/<id>/estado/` | Terminar o volver a poner en proceso (POST) | Oficina |
| `/proyecto/<id>/eliminar/` | Eliminar proyecto (POST) | Oficina |
| `/urgencias/` | Abrir urgencias y ver las abiertas | Operarios y Oficina |
| `/admin/` | Panel de administración | Superusuario |

## Puesta en marcha

    python -m venv myvenv
    myvenv\Scripts\activate          (Linux: source myvenv/bin/activate)
    pip install -r requirements.txt
    python manage.py migrate
    python manage.py loaddata grupos
    python manage.py createsuperuser
    python manage.py runserver

`loaddata grupos` crea los grupos `Operarios` y `Oficina` con sus permisos. Sin ellos el registro falla, porque cada usuario nuevo se mete en su grupo.

Para tener un usuario de Oficina, créalo desde `/admin/` con el rol Oficina y añádelo al grupo `Oficina` (el registro de la web solo crea operarios).

Los datos reales de la empresa (obras, materiales y precios) no se publican en el repositorio. Para probar, crea proyectos desde la web con un usuario de Oficina, o materiales y apuntes desde `/admin/`.

## Estructura

    mysite/            configuración del proyecto (settings, urls)
    gestion/
        models.py      Usuario, Operario, Oficina, Proyecto, Categoria, Tipo, Material, Consumo, Albaran
        forms.py       RegistroForm, ProyectoForm, UrgenciaForm
        views.py       vistas de portada, listados, detalle, CRUD, urgencias y registro
        urls.py        rutas de la aplicación
        fixtures/      grupos.json (grupos y permisos)
        templates/     plantillas (gestion/ y registration/)
        static/        CSS, JavaScript e imágenes
