from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import SaludView

urlpatterns = [
    path('api/v1/salud/', SaludView.as_view(), name='salud'),
    path('api/v1/auth/', include('apps.usuarios.urls')),
    path('api/v1/usuarios/', include('apps.usuarios.urls_management')),
    path('api/v1/financiero/', include('apps.financial.urls')),
    path('api/v1/documentos/', include('apps.documentos.urls')),
    path('api/v1/configuracion/', include('apps.configuracion.urls')),
]

if settings.ADMIN_ENABLED:
    urlpatterns.insert(0, path('admin/', admin.site.urls))

if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
