from rest_framework import serializers

from .models import Documento, RangoFecha


class AnioSerializer(serializers.Serializer):
    id = serializers.IntegerField(source='id_anio')
    anio = serializers.IntegerField()


class MesSerializer(serializers.Serializer):
    id = serializers.IntegerField(source='id_mes')
    mes = serializers.CharField()


class FinancieraSerializer(serializers.Serializer):
    id = serializers.CharField()
    nombre = serializers.CharField()


class CorporacionSerializer(serializers.Serializer):
    id = serializers.CharField()
    tipo_corporacion = serializers.CharField()
    financieras = serializers.SerializerMethodField()

    def get_financieras(self, obj):
        return FinancieraSerializer(obj.financiera_set.all(), many=True).data


class RangoFechaSerializer(serializers.ModelSerializer):
    class Meta:
        model = RangoFecha
        fields = ('desde', 'hasta')


class DocumentoSerializer(serializers.ModelSerializer):
    anio = serializers.IntegerField(source='anio_id')
    mes_id = serializers.IntegerField()
    corporacion_id = serializers.CharField()
    financiera_id = serializers.CharField()

    class Meta:
        model = Documento
        fields = (
            'id',
            'nombre_archivo',
            'ruta_archivo',
            'doc_aprobado',
            'anio',
            'mes_id',
            'corporacion_id',
            'financiera_id',
            'fecha',
            'email_usuario_sube',
            'email_usuario_aprueba',
            'fecha_aprueba',
            'email_usuario_rechaza',
            'motivo_rechazo',
            'fecha_rechaza',
            'motivo_desaprueba',
            'fecha_desaprueba',
        )


class RechazarRevocarRequestSerializer(serializers.Serializer):
    motivo = serializers.CharField(allow_blank=False)


class RangoFechasRequestSerializer(serializers.Serializer):
    desde = serializers.DateField()
    hasta = serializers.DateField()
