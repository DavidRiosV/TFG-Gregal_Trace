import os
import unicodedata

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone

class Usuario(AbstractUser):
    """Usuario que inicia sesión (Sesiones, diapositiva 9).
    Nombre, apellidos, email y contraseña ya vienen de AbstractUser."""
    # Roles de la empresa. Oficial y Peón tienen los mismos permisos (grupo «Operarios»);
    # se separan para saber qué es cada empleado. El 1 era «Operario» y pasa a ser Oficial.
    OFICIAL = 1
    OFICINA = 2
    PEON = 3
    ADMIN = 4
    OPERARIO = OFICIAL   # nombre antiguo, para el código que aún lo usa
    ROLES = (
        (OFICIAL, 'Oficial'),
        (PEON, 'Peón'),
        (OFICINA, 'Oficina'),
        (ADMIN, 'Administrador'),
    )
    # Los que trabajan en obra: apuntan horas, notas y albaranes
    ROLES_OPERARIO = (OFICIAL, PEON)
    # Por defecto Oficial (un rol con pocos permisos)
    rol = models.PositiveSmallIntegerField(choices=ROLES, default=OFICIAL)

    def es_operario(self):
        return self.rol in self.ROLES_OPERARIO

    def save(self, *args, **kwargs):
        # El superusuario (python manage.py createsuperuser) siempre tiene el rol de administrador
        if self.is_superuser:
            self.rol = self.ADMIN
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_rol_display()})"

# Modelo de operario
class Operario(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE)

    def __str__(self):
        return self.usuario.username

# Modelo de oficina
class Oficina(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE)

    def __str__(self):
        return self.usuario.username

 #Los proyectos que hay en la web ya sean obras intervencones mantenimientos o urgencias
class Proyecto(models.Model):
    #Los tipos
    TIPOS = [
        ('URG', 'Urgencia'),
        ('OBR', 'Obra'),
        ('INT', 'Intervención'),
        ('MAN', 'Mantenimiento'),
    ]
    #Estado del proyecto
    ESTADOS = [
        ('PRO', 'En proceso'),
        ('TER', 'Terminado'),
    ]

    nombre = models.CharField(max_length=150)
    # Cliente del trabajo. Texto libre: al escribirlo se sugieren los clientes que ya existen
    cliente = models.CharField(max_length=150, blank=True)
    tipo = models.CharField(max_length=3, choices=TIPOS, default='OBR')
    descripcion = models.TextField(blank=True)
    fecha_inicio = models.DateField(default=timezone.now)
    fecha_fin = models.DateField(blank=True, null=True)
    estado = models.CharField(max_length=3, choices=ESTADOS, default='PRO')

    # Cuando es una urgencia: en qué se convertirá cuando se termine
    tipo_destino = models.CharField(max_length=3, choices=TIPOS, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='proyectos_creados')

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"

def dias_texto(fecha):
    """Lo que falta (o lo que ha pasado) hasta una fecha: «hoy», «mañana», «en 4 días», «hace 3 días»."""
    dias = (fecha - timezone.now().date()).days
    if dias == 0:
        return 'hoy'
    if dias == 1:
        return 'mañana'
    if dias == -1:
        return 'ayer'
    if dias > 0:
        return f'en {dias} días'
    return f'hace {-dias} días'


def horas_texto(horas):
    """Horas en decimal (2.5) a texto (2 h 30 min)."""
    minutos = int(round(horas * 60))
    h, m = divmod(minutos, 60)
    if h and m:
        return f'{h} h {m} min'
    if m:
        return f'{m} min'
    return f'{h} h'


def sin_tildes(texto):
    """«Válvula» -> «valvula». Para que el buscador encuentre igual con o sin tildes ni mayúsculas."""
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()


def buscar_materiales(materiales, texto):
    """Materiales cuyo nombre o proveedor contiene todas las palabras buscadas, sin importar tildes
    («valvula 1/2» encuentra «Válvula de esfera 1/2"»)."""
    palabras = sin_tildes(texto).split()
    encontrados = [m.pk for m in materiales if all(p in sin_tildes(f'{m.nombre} {m.proveedor}') for p in palabras)]
    return materiales.filter(pk__in=encontrados)


#Familias del catálogo (Fontanería, Climatización...): primero se elige la familia y luego el material
class Categoria(models.Model):
    # El código corto (FON, CLI...) es la clave primaria: es lo que viaja en la URL (?categoria=FON)
    codigo = models.CharField(max_length=3, primary_key=True)
    nombre = models.CharField(max_length=60, unique=True)
    orden = models.PositiveSmallIntegerField(default=50)

    class Meta:
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre

#Tipos de material dentro de una familia (Tuberías, Válvulas, Bombas)
class Tipo(models.Model):
    nombre = models.CharField(max_length=60)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='tipos')

    class Meta:
        ordering = ['nombre']
        # Puede haber «Bombas» en Fontanería y en Piscina, pero no dos «Bombas» en la misma familia
        unique_together = ['nombre', 'categoria']

    def __str__(self):
        return f"{self.nombre} ({self.categoria})"

#Modelo para los materiales
class Material(models.Model):
    #En que se mide cada material
    UNIDADES = [
        ('UD', 'Unidad'),
        ('M', 'Metro'),
        ('M2', 'Metro cuadrado'),
        ('KG', 'Kilogramo'),
        ('L', 'Litro'),
        ('H', 'Hora'),
    ]

    nombre = models.CharField(max_length=100, unique=True)
    # Familia y tipo son modelos propios para que Oficina pueda crearlos y editarlos desde la web
    # PROTECT: no se puede borrar una familia que aún tiene materiales
    categoria = models.ForeignKey('Categoria', on_delete=models.PROTECT, default='OTR', related_name='materiales')
    # SET_NULL: si se borra un tipo, sus materiales se quedan sin tipo pero no se borran
    tipo = models.ForeignKey('Tipo', on_delete=models.SET_NULL, null=True, blank=True, related_name='materiales')
    unidad = models.CharField(max_length=2, choices=UNIDADES, default='UD')
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    # Proveedor habitual (texto libre con sugerencias de los que ya existen)
    proveedor = models.CharField(max_length=100, blank=True)
    # Clase: separa el material principal de los accesorios y los soportes (para las estadísticas).
    # Vacía en mano de obra y servicios.
    CLASES = [
        ('PRI', 'Material principal'),
        ('ACC', 'Accesorio'),
        ('SOP', 'Soporte'),
    ]
    clase = models.CharField(max_length=3, choices=CLASES, blank=True, default='PRI')

    def nombre_puesto(self):
        """En las horas, el puesto sin la palabra «Hora»: «Hora Oficial» -> «Oficial»."""
        return self.nombre.removeprefix('Hora ').strip()

    def abreviatura(self):
        # Unidad corta para mostrar junto a la cantidad: 2 h, 3 ud, 40 m
        return {'UD': 'ud', 'M': 'm', 'M2': 'm²', 'KG': 'kg', 'L': 'l', 'H': 'h'}.get(self.unidad, '')

    def __str__(self):
        return f"{self.nombre} ({self.get_unidad_display()})"

#Clase para apuntar: qué material se ha gastado, en qué proyecto y quién lo apuntó.
class CampoHora(models.Model):
    """Campo o especialidad de una hora de trabajo (Electricidad, Fontanería...).
    Junto con el puesto (Oficial, Peón...) decide el precio de la hora. Lista propia
    que Oficina crea y borra desde «Precios horas»."""
    nombre = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class TarifaHora(models.Model):
    """Precio de una hora según la combinación puesto + campo (Oficial + Electricidad = 32 €/h).
    El puesto es uno de los materiales de horas (unidad «Hora»): Hora Oficial, Hora Peón..."""
    puesto = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='tarifas',
                               limit_choices_to={'unidad': 'H'})
    campo = models.ForeignKey(CampoHora, on_delete=models.CASCADE, related_name='tarifas')
    precio = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        # Una sola tarifa por combinación
        unique_together = ('puesto', 'campo')
        ordering = ['puesto__nombre', 'campo__nombre']

    def __str__(self):
        return f'{self.puesto.nombre} · {self.campo.nombre}: {self.precio} €/h'


def precio_hora(puesto, campo):
    """Precio de una hora de ese puesto en ese campo. Si Oficina no ha fijado esa combinación,
    se usa el precio base del puesto (el del material «Hora ...»)."""
    if campo:
        tarifa = TarifaHora.objects.filter(puesto=puesto, campo=campo).first()
        if tarifa:
            return tarifa.precio
    return puesto.precio

class Consumo(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='consumos')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='consumos')
    trabajador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='consumos')
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField(default=timezone.now)
    # Solo en las horas: campo del trabajo (Electricidad, Fontanería...). Con el puesto decide el precio.
    # PROTECT: no se puede borrar un campo que ya tiene horas apuntadas (se perderían en las estadísticas).
    campo = models.ForeignKey(CampoHora, on_delete=models.PROTECT, null=True, blank=True, related_name='consumos')

    def total(self):
        return self.cantidad * self.precio_unitario

    def descripcion(self):
        """Qué se apuntó: «Tubería PPR 25 mm» o, en las horas, «Hora Oficial · Electricidad»."""
        if self.campo_id:
            return f'{self.material.nombre} · {self.campo.nombre}'
        return self.material.nombre

    def cantidad_texto(self):
        # Las horas como «2 h 30 min»; el resto como «3 ud» o «12,5 m»
        if self.material.unidad == 'H':
            return horas_texto(self.cantidad)
        return f'{self.cantidad.normalize():f}'.replace('.', ',') + ' ' + self.material.abreviatura()

    def __str__(self):
        return f"{self.cantidad} {self.material.nombre} - {self.proyecto.nombre}"

# Citas de un proyecto (visita, entrega, revisión...). Un proyecto puede tener varias
# y los listados se ordenan por la próxima.
class Cita(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='citas')
    fecha = models.DateField()
    # La hora es opcional: hay citas de todo el día
    hora = models.TimeField(blank=True, null=True)
    motivo = models.CharField(max_length=120, blank=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='citas')

    class Meta:
        ordering = ['fecha', 'hora', 'id']

    def dias(self):
        return dias_texto(self.fecha)

    def es_pasada(self):
        return self.fecha < timezone.now().date()

    def es_cercana(self):
        # Hoy o mañana: se marca en ámbar para que no se pase
        return 0 <= (self.fecha - timezone.now().date()).days <= 1

    def __str__(self):
        return f"Cita de {self.proyecto.nombre} el {self.fecha:%d/%m/%Y}"


# Notas de texto de un proyecto. Las escribe cualquier usuario
class Nota(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='notas')
    # SET_NULL: si se borra el usuario, sus notas se quedan en el proyecto
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='notas')
    texto = models.TextField(max_length=2000)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f"Nota de {self.proyecto.nombre}"


def ruta_albaran(albaran, nombre):
    # Cada albarán se guarda en la carpeta de su proyecto: media/albaranes/proyecto_12/factura.pdf
    return f'albaranes/proyecto_{albaran.proyecto_id}/{nombre}'


# Albaranes en PDF de un proyecto. Los sube cualquiera; los borra Oficina
class Albaran(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='albaranes')
    archivo = models.FileField(upload_to=ruta_albaran)
    # Proveedor o número de albarán, para reconocerlo sin abrirlo
    descripcion = models.CharField(max_length=120, blank=True)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='albaranes')
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-id']

    def nombre_archivo(self):
        # «albaranes/proyecto_12/factura.pdf» -> «factura.pdf»
        return os.path.basename(self.archivo.name)

    def tamano_texto(self):
        # Tamaño del PDF para mostrarlo: «240 KB», «1,3 MB». Vacío si el archivo ya no está
        try:
            tamano = self.archivo.size
        except (OSError, ValueError):
            return ''
        if tamano < 1024 * 1024:
            return f'{max(1, round(tamano / 1024))} KB'
        return f'{tamano / (1024 * 1024):.1f} MB'.replace('.', ',')

    def __str__(self):
        return f"Albarán de {self.proyecto.nombre}"
