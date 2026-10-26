from django.urls import path

from .views import (
    CatalogosView,
    DocumentoAprobarView,
    DocumentoRechazarView,
    DocumentoRevocarView,
    DocumentosView,
    RangoFechasView,
)

urlpatterns = [
    path('catalogos/', CatalogosView.as_view(), name='financiero-catalogos'),
    path('documentos/', DocumentosView.as_view(), name='financiero-documentos'),
    path('documentos/<int:documento_id>/aprobar/', DocumentoAprobarView.as_view(), name='financiero-aprobar'),
    path('documentos/<int:documento_id>/rechazar/', DocumentoRechazarView.as_view(), name='financiero-rechazar'),
    path('documentos/<int:documento_id>/revocar/', DocumentoRevocarView.as_view(), name='financiero-revocar'),
    path('rango-fechas/', RangoFechasView.as_view(), name='financiero-rango-fechas'),
]
