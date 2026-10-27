from rest_framework import serializers

from apps.usuarios.models import Corporacion, Financiera

from .models import Anio, Documento, Mes, RangoFecha


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
    doc_aprobado = serializers.SerializerMethodField()

    def get_doc_aprobado(self, obj: Documento) -> str:
        """En la base hay documentos con NULL; para el cliente son pendientes ('')."""
        return obj.doc_aprobado or Documento.PENDIENTE

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


def _validar_periodo(anio: int, mes: int, corporacion: str, financiera: str, campo_mes: str, campo_financiera: str) -> None:
    """El periodo debe existir y la financiera debe pertenecer a la corporación indicada."""
    errores = {}
    if not Anio.objects.filter(id_anio=anio).exists():
        errores['anio'] = 'El año indicado no existe.'
    if not Mes.objects.filter(id_mes=mes).exists():
        errores[campo_mes] = 'El mes indicado no existe.'
    if not Financiera.objects.filter(pk=financiera, corporacion_id=corporacion).exists():
        errores[campo_financiera] = 'La financiera no existe o no pertenece a la corporación indicada.'
    if errores:
        raise serializers.ValidationError(errores)


class DocumentosQuerySerializer(serializers.Serializer):
    """Parámetros de `GET /financiero/documentos/`."""

    anio = serializers.IntegerField(min_value=1)
    mes = serializers.IntegerField(min_value=1, max_value=12)
    corporacion = serializers.CharField(max_length=11)
    financiera = serializers.CharField(max_length=11)

    def validate(self, attrs):
        _validar_periodo(attrs['anio'], attrs['mes'], attrs['corporacion'], attrs['financiera'], 'mes', 'financiera')
        return attrs


class SubirDocumentoSerializer(serializers.Serializer):
    """Cuerpo (multipart) de `POST /financiero/documentos/`."""

    file = serializers.FileField()
    anio = serializers.IntegerField(min_value=1)
    mes_id = serializers.IntegerField(min_value=1, max_value=12)
    corporacion_id = serializers.CharField(max_length=11)
    financiera_id = serializers.CharField(max_length=11)

    def validate(self, attrs):
        _validar_periodo(attrs['anio'], attrs['mes_id'], attrs['corporacion_id'], attrs['financiera_id'], 'mes_id', 'financiera_id')
        return attrs


class PeriodoQuerySerializer(serializers.Serializer):
    """Parámetros de `GET /financiero/periodo/`."""

    anio = serializers.IntegerField(min_value=1)
    mes = serializers.IntegerField(min_value=1, max_value=12)
    corporacion = serializers.CharField(max_length=11)

    def validate(self, attrs):
        errores = {}
        if not Anio.objects.filter(id_anio=attrs['anio']).exists():
            errores['anio'] = 'El año indicado no existe.'
        if not Mes.objects.filter(id_mes=attrs['mes']).exists():
            errores['mes'] = 'El mes indicado no existe.'
        if not Corporacion.objects.filter(pk=attrs['corporacion']).exists():
            errores['corporacion'] = 'La corporación indicada no existe.'
        if errores:
            raise serializers.ValidationError(errores)
        return attrs


class PeriodoFilaSerializer(serializers.Serializer):
    financiera_id = serializers.CharField(source='financiera.pk')
    financiera_nombre = serializers.CharField(source='financiera.nombre')
    estado = serializers.CharField()
    documento_id = serializers.IntegerField(source='documento.id', default=None, allow_null=True)
    nombre_archivo = serializers.CharField(source='documento.nombre_archivo', default=None, allow_null=True)
    fecha = serializers.DateTimeField(source='documento.fecha', default=None, allow_null=True)
    motivo = serializers.SerializerMethodField()

    def get_motivo(self, fila: dict) -> str | None:
        """Motivo visible en la fila: el del rechazo o el de la revocación, según el estado."""
        documento = fila['documento']
        if documento is None:
            return None
        if fila['estado'] == 'rechazado':
            return documento.motivo_rechazo
        if fila['estado'] == 'revocado':
            return documento.motivo_desaprueba
        return None


class HistorialEventoSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=['subido', 'aprobado', 'rechazado', 'revocado'])
    fecha = serializers.DateTimeField()
    email = serializers.CharField(allow_null=True)
    motivo = serializers.CharField(allow_null=True)
