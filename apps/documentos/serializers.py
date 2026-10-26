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

    class Meta:
        model = Upload
        fields = ('id', 'reemplaza_a', 'fname', 'name', 'area', 'estado', 'fecha', 'tipo', 'tamanio')
