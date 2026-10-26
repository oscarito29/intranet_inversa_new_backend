from django.urls import path

from .views import (
    CategoriaDetailView,
    CategoriasView,
    DocsEtiquetasView,
    DocumentoReemplazarView,
    DocumentosView,
    EtiquetasListView,
)

urlpatterns = [
    path('categorias/', CategoriasView.as_view(), name='documentos-categorias'),
    path('categorias/<int:category_id>/', CategoriaDetailView.as_view(), name='documentos-categoria-detalle'),
    path('etiquetas/', EtiquetasListView.as_view(), name='documentos-etiquetas'),
    path('docs-etiquetas/', DocsEtiquetasView.as_view(), name='documentos-docs-etiquetas'),
    path('documentos/', DocumentosView.as_view(), name='documentos-documentos'),
    path('documentos/<int:documento_id>/reemplazar/', DocumentoReemplazarView.as_view(), name='documentos-reemplazar'),
]
