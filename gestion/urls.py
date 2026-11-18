from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('registrar/', views.registrar_usuario, name='registrar_usuario'),
    re_path(r'^proyectos/(?P<tipo>obras|intervenciones|mantenimientos)/$', views.lista_proyectos, name='lista_proyectos'),
    path('proyecto/<int:pk>/', views.detalle_proyecto, name='detalle_proyecto'),
    re_path(r'^proyectos/(?P<tipo>obras|intervenciones|mantenimientos)/nuevo/$', views.proyecto_crear, name='proyecto_crear'),
    path('proyecto/<int:pk>/editar/', views.proyecto_editar, name='proyecto_editar'),
    path('proyecto/<int:pk>/eliminar/', views.proyecto_eliminar, name='proyecto_eliminar'),
    path('proyecto/<int:pk>/estado/', views.cambiar_estado, name='cambiar_estado'),
    path('urgencias/', views.urgencias, name='urgencias'),
    # Apuntes de horas y material
    path('apunte/<int:pk>/editar/', views.consumo_editar, name='consumo_editar'),
    path('apunte/<int:pk>/eliminar/', views.consumo_eliminar, name='consumo_eliminar'),
    path('apunte/<int:pk>/repetir/', views.consumo_repetir, name='consumo_repetir'),
    # Notas, citas y albaranes
    path('nota/<int:pk>/eliminar/', views.nota_eliminar, name='nota_eliminar'),
    path('cita/<int:pk>/eliminar/', views.cita_eliminar, name='cita_eliminar'),
    path('empleados/', views.lista_empleados, name='lista_empleados'),
    path('empleados/oficina/', views.empleados_oficina, name='empleados_oficina'),
    path('empleados/nuevo/', views.empleado_crear, name='empleado_crear'),
    path('empleado/<int:pk>/editar/', views.empleado_editar, name='empleado_editar'),
    path('empleado/<int:pk>/eliminar/', views.empleado_eliminar, name='empleado_eliminar'),
    path('calendario/', views.calendario, name='calendario'),
    path('albaranes/', views.lista_albaranes, name='lista_albaranes'),
    path('albaran/<int:pk>/', views.albaran_ver, name='albaran_ver'),
    path('albaran/<int:pk>/eliminar/', views.albaran_eliminar, name='albaran_eliminar'),
    # Catálogo (Oficina): materiales, familias y tipos
    path('materiales/', views.lista_materiales, name='lista_materiales'),
    path('materiales/nuevo/', views.material_crear, name='material_crear'),
    path('material/<int:pk>/editar/', views.material_editar, name='material_editar'),
    path('material/<int:pk>/eliminar/', views.material_eliminar, name='material_eliminar'),
    path('materiales/familias/', views.lista_categorias, name='lista_categorias'),
    path('materiales/familia/<str:pk>/editar/', views.categoria_editar, name='categoria_editar'),
    path('materiales/familia/<str:pk>/eliminar/', views.categoria_eliminar, name='categoria_eliminar'),
    path('materiales/tipos/', views.lista_tipos, name='lista_tipos'),
    path('materiales/tipo/<int:pk>/editar/', views.tipo_editar, name='tipo_editar'),
    path('materiales/tipo/<int:pk>/eliminar/', views.tipo_eliminar, name='tipo_eliminar'),
]
