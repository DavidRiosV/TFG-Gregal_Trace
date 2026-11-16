from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Albaran, Categoria, Cita, Consumo, Material, Nota, Proyecto, Tipo, Usuario, buscar_materiales


class RegistroForm(UserCreationForm):
    # Solo se ofrece Operario: las cuentas de Oficina las crea la empresa desde el admin
    roles = (
        (Usuario.OPERARIO, 'Operario'),
    )
    rol = forms.ChoiceField(choices=roles, label='Rol')

    class Meta:
        model = Usuario
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'rol')
        labels = {
            'username': 'Usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellidos',
            'email': 'Correo electrónico',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El nombre sale en cada apunte, así que es obligatorio
        self.fields['first_name'].required = True

def limpiar_texto(texto):
    # Quita espacios de sobra y pone la primera letra en mayúscula: «  hotel   son vida » -> «Hotel son vida»
    texto = ' '.join(texto.split())
    return texto[:1].upper() + texto[1:]


def limpiar_cliente(cliente):
    # Si ya existe el mismo cliente con otras mayúsculas («juan pérez» y «Juan Pérez»), se usa el que ya existe
    cliente = limpiar_texto(cliente)
    if cliente:
        existente = Proyecto.objects.filter(cliente__iexact=cliente).values_list('cliente', flat=True).first()
        if existente:
            return existente
    return cliente


class UrgenciaForm(forms.ModelForm):
    class Meta:
        model = Proyecto
        fields = ['nombre', 'cliente', 'tipo_destino', 'descripcion']
        labels = {
            'nombre': 'Nombre o dirección del trabajo',
            'cliente': 'Cliente',
            'tipo_destino': '¿Qué es?',
            'descripcion': 'Descripción',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo puede convertirse en Obra, Intervención o Mantenimiento, y es obligatorio
        self.fields['tipo_destino'].choices = [
            ('', 'Elige una opción'),
            ('OBR', 'Obra'),
            ('INT', 'Intervención'),
            ('MAN', 'Mantenimiento'),
        ]
        self.fields['tipo_destino'].required = True

    def clean_cliente(self):
        return limpiar_cliente(self.cleaned_data['cliente'])

class ProyectoForm(forms.ModelForm):
    class Meta:
        model = Proyecto
        fields = ['nombre', 'cliente', 'tipo', 'descripcion', 'fecha_inicio', 'fecha_fin', 'estado']
        labels = {
            'nombre': 'Nombre o dirección',
            'cliente': 'Cliente',
            'tipo': 'Tipo',
            'descripcion': 'Descripción',
            'fecha_inicio': 'Fecha de inicio',
            'fecha_fin': 'Fecha de fin',
            'estado': 'Estado',
        }
        help_texts = {
            'cliente': 'Elige uno de la lista o escribe uno nuevo.',
        }
        widgets = {
            # list= une el campo con el <datalist> de clientes que ya existen (sugerencias al escribir)
            'cliente': forms.TextInput(attrs={'list': 'clientes', 'autocomplete': 'off'}),
            'descripcion': forms.Textarea(attrs={'rows': 4}),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'fecha_fin': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def clean_cliente(self):
        return limpiar_cliente(self.cleaned_data['cliente'])

    def clean(self):
        super().clean()

        fecha_inicio = self.cleaned_data.get('fecha_inicio')
        fecha_fin = self.cleaned_data.get('fecha_fin')
        estado = self.cleaned_data.get('estado')

        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            self.add_error('fecha_fin', 'La fecha de fin no puede ser anterior a la de inicio.')

        if estado == 'TER' and not fecha_fin:
            self.add_error('fecha_fin', 'Un proyecto terminado necesita fecha de fin.')

        if estado == 'PRO' and fecha_fin:
            self.add_error('fecha_fin', 'Un proyecto en proceso no lleva fecha de fin. Déjala vacía o márcalo como terminado.')

        return self.cleaned_data


# ---------------------------------------------------------------------------
# Apuntes de horas y de material
# ---------------------------------------------------------------------------
class ApunteForm(forms.ModelForm):
    """Base de los dos formularios de apuntar: mismos campos y misma validación."""
    class Meta:
        model = Consumo
        fields = ['material', 'cantidad', 'fecha']
        labels = {
            'material': 'Material',
            'cantidad': 'Cantidad',
            'fecha': 'Fecha',
        }
        widgets = {
            'cantidad': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'inputmode': 'decimal'}),
            'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def clean(self):
        super().clean()
        cantidad = self.cleaned_data.get('cantidad')
        material = self.cleaned_data.get('material')
        if cantidad is not None and cantidad <= 0:
            self.add_error('cantidad', 'La cantidad tiene que ser mayor que 0.')
        elif cantidad is not None and material and material.unidad == 'H':
            # Horas: de 15 en 15 minutos y como mucho 24 h
            if cantidad > 24:
                self.add_error('cantidad', 'No se pueden apuntar más de 24 horas en un apunte.')
            elif (cantidad * 4) % 1 != 0:
                self.add_error('cantidad', 'Las horas se apuntan en tramos de 15 minutos.')
        return self.cleaned_data


class HorasForm(ApunteForm):
    """Apuntar horas: tipo de hora (Oficial, Pareja, Peón o Subcontrata) y tiempo."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        horas = Material.objects.filter(unidad='H').order_by('nombre')
        # Botones de opción en vez de desplegable, sin la opción vacía «---------»
        self.fields['material'].widget = forms.RadioSelect()
        self.fields['material'].empty_label = None
        # En los botones sale «Oficial» en vez de «Hora Oficial (Hora)»
        self.fields['material'].label_from_instance = lambda material: material.nombre.replace('Hora ', '')
        self.fields['material'].queryset = horas
        self.fields['material'].label = 'Tipo de hora'
        # La cantidad la escribe el selector de horas y minutos (main.js)
        self.fields['cantidad'].widget = forms.HiddenInput()
        if not self.is_bound and not self.instance.pk:
            self.initial['cantidad'] = 1
            if horas:
                self.initial['material'] = horas[0].pk


class ConsumoForm(ApunteForm):
    """Apuntar material (Oficina). Se le pasan la familia, el tipo y lo buscado para filtrar
    la lista, igual que el formulario que recibe datos extra (Sesiones, diapositivas 26-27)."""

    def __init__(self, *args, categoria=None, tipo=None, busqueda=None, **kwargs):
        super().__init__(*args, **kwargs)
        materiales = Material.objects.exclude(unidad='H').select_related('tipo').order_by('tipo__nombre', 'nombre')
        if busqueda:
            # El buscador mira en todo el catálogo, sin importar la familia
            materiales = buscar_materiales(materiales, busqueda)
        elif categoria:
            materiales = materiales.filter(categoria=categoria)
            if tipo:
                materiales = materiales.filter(tipo=tipo)
        else:
            # Sin familia ni búsqueda todavía no se ofrece nada
            materiales = materiales.none()
        self.fields['material'].queryset = materiales

        # Para la plantilla: los materiales agrupados por tipo (Tuberías, Válvulas...)
        self.agrupados = {}
        for material in materiales:
            nombre_tipo = material.tipo.nombre if material.tipo else 'Otros'
            self.agrupados.setdefault(nombre_tipo, []).append(material)
        # Si solo hay un material posible, se deja marcado
        if len(materiales) == 1 and not self.is_bound and not self.instance.pk:
            self.initial['material'] = materiales[0].pk


# ---------------------------------------------------------------------------
# Notas, albaranes y citas del proyecto
# ---------------------------------------------------------------------------
class NotaForm(forms.ModelForm):
    class Meta:
        model = Nota
        fields = ['texto']
        labels = {'texto': 'Nueva nota'}
        error_messages = {'texto': {'required': 'La nota está vacía.'}}
        widgets = {
            'texto': forms.Textarea(attrs={'rows': 3, 'maxlength': 2000,
                                           'placeholder': 'Algo que deba saber el resto: acceso, llaves, lo que falta...'}),
        }


class AlbaranForm(forms.ModelForm):
    TAMANO_MAXIMO = 10 * 1024 * 1024   # 10 MB

    class Meta:
        model = Albaran
        fields = ['archivo', 'descripcion']
        labels = {
            'archivo': 'Albarán en PDF',
            'descripcion': 'Proveedor o número de albarán',
        }
        widgets = {
            # accept: el móvil y el ordenador solo ofrecen archivos PDF al elegir
            'archivo': forms.FileInput(attrs={'accept': 'application/pdf,.pdf'}),
        }
        error_messages = {'archivo': {'required': 'Elige el PDF del albarán.'}}

    def clean_archivo(self):
        archivo = self.cleaned_data['archivo']
        # Se comprueba la extensión, el tamaño y que de verdad sea un PDF (empieza por «%PDF-»)
        if not archivo.name.lower().endswith('.pdf'):
            raise forms.ValidationError('Solo se pueden subir archivos PDF.')
        if archivo.size > self.TAMANO_MAXIMO:
            raise forms.ValidationError('El PDF ocupa más de 10 MB.')
        cabecera = archivo.read(5)
        archivo.seek(0)
        if cabecera != b'%PDF-':
            raise forms.ValidationError('El archivo no es un PDF válido.')
        return archivo

    def clean_descripcion(self):
        return ' '.join(self.cleaned_data['descripcion'].split())


class CitaForm(forms.ModelForm):
    class Meta:
        model = Cita
        fields = ['fecha', 'hora', 'motivo']
        labels = {
            'fecha': 'Fecha',
            'hora': 'Hora',
            'motivo': 'Motivo',
        }
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'hora': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'motivo': forms.TextInput(attrs={'placeholder': 'Visita, entrega, revisión...', 'maxlength': 120}),
        }
        error_messages = {'fecha': {'required': 'Elige el día de la cita.'}}

    def clean_motivo(self):
        return limpiar_texto(self.cleaned_data['motivo'])


# ---------------------------------------------------------------------------
# Catálogo (Oficina): materiales, familias y tipos
# ---------------------------------------------------------------------------
class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ['nombre', 'categoria', 'tipo', 'clase', 'unidad', 'precio', 'proveedor']
        labels = {
            'nombre': 'Nombre',
            'categoria': 'Familia',
            'tipo': 'Tipo',
            'clase': 'Clase',
            'unidad': 'Unidad',
            'precio': 'Precio por unidad (€)',
            'proveedor': 'Proveedor',
        }
        help_texts = {
            'precio': 'Cambiar el precio no modifica los apuntes ya hechos: cada apunte guarda el precio de su día.',
            'proveedor': 'Elige uno de la lista o escribe uno nuevo.',
        }
        error_messages = {'nombre': {'unique': 'Ya hay un material con ese nombre.'}}
        widgets = {
            'clase': forms.RadioSelect(),
            'precio': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'inputmode': 'decimal'}),
            'proveedor': forms.TextInput(attrs={'list': 'proveedores', 'autocomplete': 'off'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Familia obligatoria y sin la opción vacía «---------»
        self.fields['categoria'].empty_label = None
        self.fields['tipo'].empty_label = 'Sin tipo'
        self.fields['tipo'].queryset = Tipo.objects.select_related('categoria').order_by('categoria__orden', 'nombre')
        # Las tres clases y, al final, «Sin clase» para mano de obra y servicios
        self.fields['clase'].choices = Material.CLASES + [('', 'Sin clase (mano de obra)')]

    def clean(self):
        super().clean()
        categoria = self.cleaned_data.get('categoria')
        tipo = self.cleaned_data.get('tipo')
        if categoria and tipo and tipo.categoria != categoria:
            self.add_error('tipo', f'El tipo «{tipo.nombre}» es de {tipo.categoria.nombre}, no de {categoria.nombre}.')
        precio = self.cleaned_data.get('precio')
        if precio is not None and precio < 0:
            self.add_error('precio', 'El precio no puede ser negativo.')
        # Proveedor: si ya existe escrito con otras mayúsculas, se usa el que ya hay
        proveedor = limpiar_texto(self.cleaned_data.get('proveedor', ''))
        if proveedor:
            existente = Material.objects.filter(proveedor__iexact=proveedor).values_list('proveedor', flat=True).first()
            proveedor = existente or proveedor
        self.cleaned_data['proveedor'] = proveedor
        return self.cleaned_data


class CategoriaForm(forms.ModelForm):
    """Familias del catálogo. El código de 3 letras lo pone la vista al crearla."""
    class Meta:
        model = Categoria
        fields = ['nombre', 'orden']
        labels = {
            'nombre': 'Nombre de la familia',
            'orden': 'Posición',
        }
        help_texts = {'orden': 'Las familias salen ordenadas de menor a mayor.'}
        error_messages = {'nombre': {'unique': 'Ya hay una familia con ese nombre.'}}
        widgets = {'orden': forms.NumberInput(attrs={'min': '0', 'step': '1'})}

    def clean_nombre(self):
        return limpiar_texto(self.cleaned_data['nombre'])


class TipoForm(forms.ModelForm):
    class Meta:
        model = Tipo
        fields = ['nombre', 'categoria']
        labels = {
            'nombre': 'Nombre del tipo',
            'categoria': 'Familia',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].empty_label = None

    def clean(self):
        super().clean()
        nombre = self.cleaned_data.get('nombre')
        categoria = self.cleaned_data.get('categoria')
        if nombre:
            nombre = limpiar_texto(nombre)
            self.cleaned_data['nombre'] = nombre
            # unique_together: no puede haber dos tipos con el mismo nombre en la misma familia
            repetido = Tipo.objects.filter(nombre__iexact=nombre, categoria=categoria).exclude(pk=self.instance.pk)
            if categoria and repetido.exists():
                self.add_error('nombre', f'Ya hay un tipo «{nombre}» en {categoria.nombre}.')
        return self.cleaned_data
