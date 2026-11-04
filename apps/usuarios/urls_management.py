from django.urls import path

from .views_management import (
    CorporacionesListView,
    DirectorioView,
    FinancierasListView,
    RolesListView,
    UsuarioDetailView,
    UsuarioRestablecerPasswordView,
    UsuariosListCreateView,
)

urlpatterns = [
    path('', UsuariosListCreateView.as_view(), name='usuarios-list-create'),
    path('directorio/', DirectorioView.as_view(), name='usuarios-directorio'),
    path('<int:pk>/', UsuarioDetailView.as_view(), name='usuarios-detail'),
    path('<int:pk>/restablecer-password/', UsuarioRestablecerPasswordView.as_view(), name='usuarios-restablecer-password'),
    path('roles/', RolesListView.as_view(), name='usuarios-roles'),
    path('financieras/', FinancierasListView.as_view(), name='usuarios-financieras'),
    path('corporaciones/', CorporacionesListView.as_view(), name='usuarios-corporaciones'),
]
