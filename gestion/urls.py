from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    # Expresión regular: solo admite los tres apartados; cualquier otra palabra da 404
    re_path(r'^proyectos/(?P<tipo>obras|intervenciones|mantenimientos)/$', views.lista_proyectos, name='lista_proyectos'),
    path('proyecto/<int:pk>/', views.detalle_proyecto, name='detalle_proyecto'),
]