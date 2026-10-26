from django.urls import path

from .views_management import (
    CorporacionesListView,
    FinancierasListView,
    RolesListView,
    UsuarioDetailView,
    UsuariosListCreateView,
)

urlpatterns = [
    path('', UsuariosListCreateView.as_view(), name='usuarios-list-create'),
    path('<int:pk>/', UsuarioDetailView.as_view(), name='usuarios-detail'),
    path('roles/', RolesListView.as_view(), name='usuarios-roles'),
    path('financieras/', FinancierasListView.as_view(), name='usuarios-financieras'),
    path('corporaciones/', CorporacionesListView.as_view(), name='usuarios-corporaciones'),
]
