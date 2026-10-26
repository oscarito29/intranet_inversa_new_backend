from django.urls import path

from .views import (
    ActividadesView,
    ComunicadoDetailView,
    ComunicadosView,
    CumpleañosView,
    EtiquetaDetailView,
    EtiquetaRolesView,
    EtiquetasView,
    ImagenDetailView,
    ImagenesView,
    RolesView,
)

urlpatterns = [
    path('roles/', RolesView.as_view(), name='configuracion-roles'),
    path('etiquetas/', EtiquetasView.as_view(), name='configuracion-etiquetas'),
    path('etiquetas/<int:etiqueta_id>/', EtiquetaDetailView.as_view(), name='configuracion-etiqueta-detail'),
    path('etiqueta-roles/', EtiquetaRolesView.as_view(), name='configuracion-etiqueta-roles'),
    path('imagenes/', ImagenesView.as_view(), name='configuracion-imagenes'),
    path('imagenes/<int:imagen_id>/', ImagenDetailView.as_view(), name='configuracion-imagen-detail'),
    path('comunicados/', ComunicadosView.as_view(), name='configuracion-comunicados'),
    path('comunicados/<int:comunicado_id>/', ComunicadoDetailView.as_view(), name='configuracion-comunicado-detail'),
    path('actividades/', ActividadesView.as_view(), name='configuracion-actividades'),
    path('cumpleanos/', CumpleañosView.as_view(), name='configuracion-cumpleanos'),
]
