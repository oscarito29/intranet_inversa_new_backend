from django.urls import path

from .views import CambiarPasswordView, LoginView, LogoutView, MeView, PerfilFotoView, PerfilView, RefreshView

urlpatterns = [
    path('token/', LoginView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', RefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('perfil/', PerfilView.as_view(), name='perfil'),
    path('perfil/foto/', PerfilFotoView.as_view(), name='perfil-foto'),
    path('password/', CambiarPasswordView.as_view(), name='cambiar-password'),
]
