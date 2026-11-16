# Gregal Trace

Aplicación web con Django para **Instalaciones Gregal**. Sirve para registrar el material y las horas que se gastan en cada obra, intervención y mantenimiento, y saber así cuánto cuesta y cuánto tarda cada trabajo.

Proyecto Integrado de 2.º DAW (IES Polígono Sur) · David Ríos Valencia.

## Tecnologías

- Python 3.12 y Django 5.1
- SQLite en desarrollo y PostgreSQL 16 en Docker
- django-environ para leer la configuración secreta del archivo `.env`
- Docker y Docker Compose, con Gunicorn como servidor de la aplicación y Nginx delante
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

## Puesta en marcha (en local, sin Docker)

    python -m venv myvenv
    myvenv\Scripts\activate          (Linux: source myvenv/bin/activate)
    pip install -r requirements.txt

Crea un archivo `.env` junto a `manage.py` con al menos:

    SECRET_KEY=una-clave-larga-y-aleatoria
    DEBUG=True

y después:

    python manage.py migrate
    python manage.py loaddata grupos datos_prueba
    python manage.py runserver

- `grupos` crea los grupos `Operarios` y `Oficina` con sus permisos. Sin ellos el registro falla, porque cada usuario nuevo se mete en su grupo.
- `datos_prueba` carga un catálogo de ejemplo, proyectos y apuntes inventados, y estos usuarios:

| Rol | Usuario | Contraseña |
|---|---|---|
| Oficina | `oficina` | `Gregal-Oficina-26` |
| Operarios | `joan`, `miquel`, `aina`, `tomeu`, `xisco`, `laura` | `Prueba2026` |

Los datos reales de la empresa (obras, materiales y precios) no se publican en el repositorio: todo lo de `datos_prueba` es inventado.

Variables opcionales del `.env` (si no se ponen, se usan los valores por defecto):

| Variable | Para qué | Por defecto |
|---|---|---|
| `ALLOWED_HOSTS` | Direcciones desde las que se abre la web, separadas por comas | `127.0.0.1,localhost,davidrv.pythonanywhere.com` |
| `CSRF_TRUSTED_ORIGINS` | Webs de confianza para los formularios cuando hay Nginx o HTTPS | vacío |
| `DATABASE_URL` | Base de datos | `sqlite:///db.sqlite3` |

## Despliegue con Docker

La aplicación se despliega en tres contenedores, siguiendo la misma arquitectura del despliegue en la nube de los apuntes (Ubuntu + PostgreSQL + Gunicorn + Nginx), pero con cada pieza en su contenedor:

    Navegador ──► nginx (puerto 8080) ──► web: Django + Gunicorn (puerto 8000) ──► db: PostgreSQL 16
                    └─ sirve /static/ directamente

| Contenedor | Imagen | Qué hace |
|---|---|---|
| `db` | `postgres:16` | Base de datos. Sus datos se guardan en el volumen `datos_db` |
| `web` | se construye con el `Dockerfile` | Al arrancar hace `migrate` y `collectstatic` y lanza Gunicorn con 3 procesos |
| `nginx` | `nginx:1.27` | Recibe las peticiones en el puerto 8080, sirve los estáticos y pasa el resto a Gunicorn |

Archivos del despliegue:

| Archivo | Contenido |
|---|---|
| `Dockerfile` | Imagen de la web: Python 3.12, instala `requirements.txt`, copia el proyecto y arranca Gunicorn |
| `docker-compose.yml` | Los tres contenedores, sus volúmenes (`datos_db`, `estaticos`, `media`) y el orden de arranque (la web espera a que PostgreSQL esté listo) |
| `docker/nginx.conf` | Configuración de Nginx como proxy inverso |
| `.dockerignore` | Lo que no entra en la imagen: entorno virtual, `.env`, base de datos local y datos reales de la empresa |
| `.env.docker.example` | Plantilla de las variables de Docker |

### Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (en Windows, con WSL 2) o Docker Engine en Linux.
- Comprobar que funciona: `docker --version`, `docker compose version` y `docker run hello-world`.

### Pasos

1. Descargar el proyecto:

        git clone https://github.com/DavidRiosV/TFG-Gregal_Trace.git
        cd TFG-Gregal_Trace

2. Crear el archivo de variables a partir de la plantilla y **cambiar las claves** (`SECRET_KEY` y la contraseña de PostgreSQL, que debe ser la misma en `POSTGRES_PASSWORD` y en `DATABASE_URL`):

        copy .env.docker.example .env.docker        (Linux: cp .env.docker.example .env.docker)

3. Construir la imagen y arrancar los tres contenedores:

        docker compose up -d --build

4. Comprobar que están en marcha (`db` debe aparecer como *healthy*):

        docker compose ps

5. Cargar los permisos y los datos de prueba:

        docker compose exec web python manage.py loaddata grupos datos_prueba

6. Abrir **http://localhost:8080** y entrar con los usuarios de la tabla anterior.

Opcional, para el panel `/admin/`:

    docker compose exec web python manage.py createsuperuser

### Comandos útiles

| Comando | Para qué |
|---|---|
| `docker compose logs web` | Ver el registro de Django y Gunicorn (errores incluidos) |
| `docker compose ps` | Estado de los contenedores |
| `docker compose up -d --build` | Volver a construir y arrancar tras cambiar el código |
| `docker compose down` | Parar los contenedores (los datos se conservan en los volúmenes) |
| `docker compose down -v` | Parar y **borrar también los datos** para empezar de cero |

### Notas

- En Docker la web funciona con `DEBUG=False`: los estáticos los sirve Nginx, no Django.
- `.env.docker` contiene claves y no se sube a GitHub (está en `.gitignore`). Al contenedor se le pasan las variables con `env_file`, nunca van dentro de la imagen.
- Los archivos subidos (albaranes) se guardan en el volumen `media` y Nginx no los publica: solo se abren desde la aplicación con la sesión iniciada.
- La producción del proyecto sigue en PythonAnywhere (https://davidrv.pythonanywhere.com), que no ejecuta contenedores. Docker sirve para desplegar la aplicación en cualquier servidor propio con un solo comando.

## Estructura

    mysite/            configuración del proyecto (settings, urls)
    gestion/
        models.py      Usuario, Operario, Oficina, Proyecto, Categoria, Tipo, Material, Consumo, Albaran
        forms.py       RegistroForm, ProyectoForm, UrgenciaForm
        views.py       vistas de portada, listados, detalle, CRUD, urgencias y registro
        urls.py        rutas de la aplicación
        fixtures/      grupos.json (grupos y permisos) y datos_prueba.json (datos inventados)
        templates/     plantillas (gestion/ y registration/)
        static/        CSS, JavaScript e imágenes
    docker/            nginx.conf (Nginx para Docker)
    Dockerfile         imagen de la aplicación
    docker-compose.yml contenedores db, web y nginx
