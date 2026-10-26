from rest_framework import serializers

from apps.documentos.models import Etiqueta, EtiquetaRol
from apps.usuarios.models import Rol, Usuario

from .models import Actividad, Comunicado, Imagen


class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ('id', 'name')


class EtiquetaSerializer(serializers.ModelSerializer):
    etiquetaNombre = serializers.CharField(source='etiqueta_nombre', allow_null=True)
    parent_id = serializers.IntegerField(allow_null=True, required=False)

    class Meta:
        model = Etiqueta
        fields = ('id', 'etiquetaNombre', 'parent_id')


class EtiquetaRolSerializer(serializers.ModelSerializer):
    etiqueta_id = serializers.IntegerField()
    rol_id = serializers.IntegerField()

    class Meta:
        model = EtiquetaRol
        fields = ('id', 'etiqueta_id', 'rol_id')


class SaveEtiquetaRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    etiquetaNombre = serializers.CharField(max_length=100)
    parent_id = serializers.IntegerField(required=False, allow_null=True)
    rolesPermitidos = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class ImagenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Imagen
        fields = ('id', 'archivo', 'ruta_img', 'puesto', 'creado_en')


class ComunicadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comunicado
        fields = ('id', 'titulo', 'contenido', 'imagen', 'usuario_sube', 'fecha_subida')


class SaveComunicadoRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    titulo = serializers.CharField(max_length=100)
    contenido = serializers.CharField(max_length=700)


class ActividadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Actividad
        fields = ('id', 'fecha', 'titulo', 'descripcion', 'hora_desde', 'hora_hasta')


class CumpleañoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ('id', 'name', 'fecha_nacimiento')
