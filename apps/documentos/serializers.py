from django.utils.encoding import filepath_to_uri
from rest_framework import serializers

from .models import Category, Etiqueta, Upload


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'description', 'created_at', 'modified_at', 'estado')


class CategoryWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=35)
    description = serializers.CharField(max_length=80)


class TagSerializer(serializers.ModelSerializer):
    etiquetaNombre = serializers.CharField(source='etiqueta_nombre')
    parent_id = serializers.IntegerField(allow_null=True)

    class Meta:
        model = Etiqueta
        fields = ('id', 'etiquetaNombre', 'parent_id')


class DocumentSerializer(serializers.ModelSerializer):
    reemplaza_a = serializers.IntegerField(source='reemplaza_a_id', allow_null=True)
    area = serializers.IntegerField(source='area_id')
    fname = serializers.SerializerMethodField()

    class Meta:
        model = Upload
        fields = ('id', 'reemplaza_a', 'fname', 'name', 'area', 'estado', 'fecha', 'tipo', 'tamanio')

    def get_fname(self, obj: Upload) -> str:
        """`upload.fname` legado: URLs de S3 ya son absolutas; el resto son nombres de
        archivo sueltos de antes de la migración, servidos ahora desde
        `media/legacy-documentos/` (ver copia hecha en la migración)."""
        if obj.fname.startswith('http://') or obj.fname.startswith('https://'):
            return obj.fname
        return f'/media/legacy-documentos/{filepath_to_uri(obj.fname)}'


class _IdsField(serializers.ListField):
    """Lista de ids enviada como claves repetidas de multipart; ignora valores en blanco."""

    child = serializers.IntegerField()

    def get_value(self, dictionary):
        if hasattr(dictionary, 'getlist') and self.field_name in dictionary:
            return [v for v in dictionary.getlist(self.field_name) if str(v).strip()]
        return super().get_value(dictionary)


class DocumentoSubidaSerializer(serializers.Serializer):
    """Cuerpo (multipart) de subir o reemplazar un documento institucional."""

    file = serializers.FileField()
    name = serializers.CharField(max_length=200)
    area = serializers.IntegerField()
    tagIds = _IdsField(required=False, default=list)

    def validate_area(self, valor: int) -> int:
        if not Category.objects.filter(pk=valor).exists():
            raise serializers.ValidationError('La categoría no existe.')
        return valor

    def validate_tagIds(self, valor: list[int]) -> list[int]:
        ids = set(valor)
        if ids and Etiqueta.objects.filter(pk__in=ids).count() != len(ids):
            raise serializers.ValidationError('Alguna etiqueta indicada no existe.')
        return list(ids)
