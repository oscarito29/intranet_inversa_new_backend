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


class ActividadWriteSerializer(serializers.Serializer):
    """Entrada de crear o editar una actividad. Las horas son opcionales; una cadena vacía cuenta como «sin hora»."""

    fecha = serializers.DateField()
    titulo = serializers.CharField(max_length=255)
    descripcion = serializers.CharField(required=False, allow_blank=True, default='')
    hora_desde = serializers.TimeField(required=False, allow_null=True, default=None)
    hora_hasta = serializers.TimeField(required=False, allow_null=True, default=None)

    def to_internal_value(self, data):
        datos = data.copy() if hasattr(data, 'copy') else dict(data)
        for campo in ('hora_desde', 'hora_hasta'):
            if datos.get(campo) == '':
                datos[campo] = None
        return super().to_internal_value(datos)

    def validate(self, attrs):
        desde, hasta = attrs.get('hora_desde'), attrs.get('hora_hasta')
        if desde and hasta and hasta < desde:
            raise serializers.ValidationError({'hora_hasta': 'La hora final no puede ser anterior a la inicial.'})
        return attrs


class CumpleañoSerializer(serializers.ModelSerializer):
    """Lo ve cualquier usuario: solo el día y el mes, nunca el año de nacimiento."""

    cumple_dia = serializers.SerializerMethodField()
    cumple_mes = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ('id', 'name', 'cumple_dia', 'cumple_mes')

    def get_cumple_dia(self, usuario: Usuario) -> int:
        return usuario.fecha_nacimiento.day

    def get_cumple_mes(self, usuario: Usuario) -> int:
        return usuario.fecha_nacimiento.month


class BitacoraSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    usuario = serializers.CharField()
    accion = serializers.CharField()
    descripcion = serializers.CharField()
    fecha = serializers.DateTimeField()


class BitacoraConsultaSerializer(serializers.Serializer):
    """Parámetros de `GET /configuracion/bitacora/`."""

    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default='')
    accion = serializers.CharField(required=False, allow_blank=True, max_length=100, default='')
    desde = serializers.DateField(required=False, default=None)
    hasta = serializers.DateField(required=False, default=None)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=25)

    def validate(self, atributos):
        if atributos['desde'] and atributos['hasta'] and atributos['hasta'] < atributos['desde']:
            raise serializers.ValidationError({'hasta': 'La fecha final no puede ser anterior a la inicial.'})
        return atributos
