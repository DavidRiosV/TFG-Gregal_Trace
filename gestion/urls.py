from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('registrar/', views.registrar_usuario, name='registrar_usuario'),
    re_path(r'^proyectos/(?P<tipo>obras|intervenciones|mantenimientos)/$', views.lista_proyectos, name='lista_proyectos'),
    path('proyecto/<int:pk>/', views.detalle_proyecto, name='detalle_proyecto'),
    re_path(r'^proyectos/(?P<tipo>obras|intervenciones|mantenimientos)/nuevo/$', views.proyecto_crear, name='proyecto_crear'),
]