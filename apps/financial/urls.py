from django.urls import path

from .views import (
    CatalogosView,
    DocumentoAprobarView,
    DocumentoHistorialView,
    DocumentoRechazarView,
    DocumentoRevocarView,
    DocumentosView,
    PeriodoView,
    RangoFechasView,
    ResumenView,
)

urlpatterns = [
    path('catalogos/', CatalogosView.as_view(), name='financiero-catalogos'),
    path('resumen/', ResumenView.as_view(), name='financiero-resumen'),
    path('periodo/', PeriodoView.as_view(), name='financiero-periodo'),
    path('documentos/', DocumentosView.as_view(), name='financiero-documentos'),
    path('documentos/<int:documento_id>/historial/', DocumentoHistorialView.as_view(), name='financiero-historial'),
    path('documentos/<int:documento_id>/aprobar/', DocumentoAprobarView.as_view(), name='financiero-aprobar'),
    path('documentos/<int:documento_id>/rechazar/', DocumentoRechazarView.as_view(), name='financiero-rechazar'),
    path('documentos/<int:documento_id>/revocar/', DocumentoRevocarView.as_view(), name='financiero-revocar'),
    path('rango-fechas/', RangoFechasView.as_view(), name='financiero-rango-fechas'),
]
