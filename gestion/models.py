from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone

# Create your models here.

class Usuario(AbstractUser):
    """Usuario que inicia sesión (Sesiones, diapositiva 9).
    Nombre, apellidos, email y contraseña ya vienen de AbstractUser."""
    OPERARIO = 1
    OFICINA = 2
    ROLES = (
        (OPERARIO, 'Operario'),
        (OFICINA, 'Oficina'),
    )
    # Por defecto Operario (el rol con menos permisos)
    rol = models.PositiveSmallIntegerField(choices=ROLES, default=OPERARIO)

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
        return self.usuario.usernam

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
    tipo = models.CharField(max_length=3, choices=TIPOS, default='OBR')
    descripcion = models.TextField(blank=True)
    fecha_inicio = models.DateField(default=timezone.now)
    fecha_fin = models.DateField(blank=True, null=True)
    # Fecha prevista de entrega (plazo). Distinta de fecha_fin, que es cuando se terminó de verdad.
    fecha_entrega = models.DateField(blank=True, null=True)
    estado = models.CharField(max_length=3, choices=ESTADOS, default='PRO')

    # Cuando es una urgencia: en qué se convertirá cuando se termine
    tipo_destino = models.CharField(max_length=3, choices=TIPOS, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='proyectos_creados')

    def plazo(self):
        # Cómo va de plazo un proyecto en proceso: 'vencido', 'cerca' (7 días o menos) o '' si va bien o no tiene
        if self.estado == 'TER' or not self.fecha_entrega:
            return ''
        dias = (self.fecha_entrega - timezone.now().date()).days
        if dias < 0:
            return 'vencido'
        if dias <= 7:
            return 'cerca'
        return ''

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"

#Familias del catálogo (Fontanería, Climatización...): primero se elige la familia y luego el material
class Categoria(models.Model):
    # El código corto (FON, CLI...) es la clave primaria: es lo que viaja en la URL (?categoria=FON)
    codigo = models.CharField(max_length=3, primary_key=True)
    nombre = models.CharField(max_length=60, unique=True)
    # Posición en la que sale en los botones de familias (de menor a mayor)
    orden = models.PositiveSmallIntegerField(default=50)

    class Meta:
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre

#Tipos de material dentro de una familia (Tuberías, Válvulas, Bombas...)
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

    def __str__(self):
        return f"{self.nombre} ({self.get_unidad_display()})"

#Clase para apuntar: qué material se ha gastado, en qué proyecto y quién lo apuntó.
class Consumo(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='consumos')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='consumos')
    trabajador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='consumos')
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.cantidad} {self.material.nombre} - {self.proyecto.nombre}"

#Clase para la implementacion de los albaranes en el hito 3
class Albaran(models.Model):
    """Preparado para el apartado de albaranes del Hito 3."""
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='albaranes')
    archivo = models.FileField(upload_to='albaranes/%Y/%m/')
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='albaranes')
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Albarán de {self.proyecto.nombre}"
