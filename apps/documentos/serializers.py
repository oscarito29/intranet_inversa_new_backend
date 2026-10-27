from django.utils.encoding import filepath_to_uri
from rest_framework import serializers

from apps.core.archivos import archivo_local_disponible

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


def url_de_archivo(fname: str) -> str:
    """
    `upload.fname` mezcla tres formatos: URLs de S3 y rutas `/media/...` (subidas nuevas) ya sirven tal cual;
    el resto son nombres sueltos de antes de la migración, servidos desde `media/legacy-documentos/`.
    """
    if fname.startswith(('http://', 'https://', '/')):
        return fname
    return f'/media/legacy-documentos/{filepath_to_uri(fname)}'


class DocumentSerializer(serializers.ModelSerializer):
    reemplaza_a = serializers.IntegerField(source='reemplaza_a_id', allow_null=True)
    area = serializers.IntegerField(source='area_id')
    fname = serializers.SerializerMethodField()

    class Meta:
        model = Upload
        fields = ('id', 'reemplaza_a', 'fname', 'name', 'area', 'estado', 'fecha', 'tipo', 'tamanio')

    def get_fname(self, obj: Upload) -> str:
        return url_de_archivo(obj.fname)


class DocumentoListaSerializer(DocumentSerializer):
    """Fila de la lista: el documento vigente con su archivo comprobado, sus etiquetas y las versiones que reemplazó."""

    disponible = serializers.SerializerMethodField()
    etiquetas = serializers.SerializerMethodField()
    versiones = serializers.SerializerMethodField()

    class Meta(DocumentSerializer.Meta):
        fields = (*DocumentSerializer.Meta.fields, 'disponible', 'etiquetas', 'versiones')

    def get_disponible(self, obj: Upload) -> bool:
        return archivo_local_disponible(url_de_archivo(obj.fname))

    def get_etiquetas(self, obj: Upload) -> list[int]:
        return self.context['etiquetas'].get(obj.id, [])

    def get_versiones(self, obj: Upload) -> list[dict]:
        return [
            {
                'id': version.id,
                'name': version.name,
                'fname': url_de_archivo(version.fname),
                'fecha': version.fecha,
                'disponible': archivo_local_disponible(url_de_archivo(version.fname)),
            }
            for version in self.context['versiones'].get(obj.id, [])
        ]


class DocumentosConsultaSerializer(serializers.Serializer):
    """Parámetros de `GET /documentos/documentos/`."""

    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default='')
    categoria = serializers.IntegerField(required=False, min_value=1, default=None)
    etiquetas = serializers.CharField(required=False, allow_blank=True, default='')
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)

    def validate_etiquetas(self, valor: str) -> tuple[int, ...]:
        try:
            return tuple(int(parte) for parte in valor.split(',') if parte.strip())
        except ValueError:
            raise serializers.ValidationError('Las etiquetas deben ser ids separados por comas.')


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
