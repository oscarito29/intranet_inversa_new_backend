from datetime import datetime

from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from . import selectors
from .models import Corporacion, Financiera, Rol, Usuario


class UsuarioSerializer(serializers.ModelSerializer):
    rol_id = serializers.IntegerField(source='rol.id', read_only=True)
    rol_nombre = serializers.CharField(source='rol.name', read_only=True)
    financiera_id = serializers.CharField(source='financiera.id', read_only=True)

    class Meta:
        model = Usuario
        fields = (
            'id',
            'name',
            'email',
            'rol_id',
            'rol_nombre',
            'financiera_id',
            'marca_id',
            'picture',
        )


class PerfilSerializer(serializers.ModelSerializer):
    rol_nombre = serializers.CharField(source='rol.name', read_only=True)
    financiera_nombre = serializers.CharField(source='financiera.nombre', read_only=True)
    puede_editar_email = serializers.SerializerMethodField()
    ultimo_cambio_password = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = (
            'id',
            'name',
            'email',
            'phone_number',
            'picture',
            'rol_nombre',
            'financiera_nombre',
            'fecha_nacimiento',
            'puede_editar_email',
            'ultimo_cambio_password',
        )

    def get_puede_editar_email(self, obj: Usuario) -> bool:
        return obj.rol_id != 2

    def get_ultimo_cambio_password(self, obj: Usuario) -> datetime | None:
        """Fecha del último cambio de contraseña hecho desde la intranet; `None` si nunca se cambió aquí."""
        return selectors.ultimo_cambio_de_password(obj)


class PerfilUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=3, max_length=30)
    phone_number = serializers.CharField(max_length=15)
    email = serializers.EmailField(max_length=255, required=False)


class CambiarPasswordSerializer(serializers.Serializer):
    actual = serializers.CharField()
    nuevo = serializers.CharField(min_length=8)
    repetido = serializers.CharField()

    def validate(self, attrs):
        if attrs['nuevo'] != attrs['repetido']:
            raise serializers.ValidationError({'repetido': 'Las contraseñas no coinciden.'})
        return attrs


class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ('id', 'name')


class CorporacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Corporacion
        fields = ('id', 'tipo_corporacion')


class FinancieraSerializer(serializers.ModelSerializer):
    id_corporacion = serializers.CharField(source='corporacion_id')

    class Meta:
        model = Financiera
        fields = ('id', 'nombre', 'id_corporacion')


class UsuarioListSerializer(serializers.ModelSerializer):
    """Espejo exacto de `UserDto` en el frontend (`features/users/api/user.dto.ts`)."""

    userFinancieraId = serializers.CharField(source='financiera_id')
    rol_id = serializers.IntegerField()

    class Meta:
        model = Usuario
        fields = (
            'id',
            'name',
            'email',
            'phone_number',
            'address',
            'picture',
            'rol_id',
            'estado',
            'userFinancieraId',
            'fecha_nacimiento',
        )


class UsuarioWriteSerializer(serializers.ModelSerializer):
    """Espejo de `CreateUserDto`/`UpdateUserDto`. `password` es opcional al editar."""

    userFinancieraId = serializers.CharField(source='financiera_id')
    rol_id = serializers.IntegerField()
    # allow_blank=True porque el frontend manda '' al editar sin cambiar la contraseña.
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Usuario
        fields = (
            'id',
            'name',
            'email',
            'phone_number',
            'address',
            'rol_id',
            'estado',
            'userFinancieraId',
            'fecha_nacimiento',
            'password',
        )
        read_only_fields = ('id',)

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        if not password:
            raise serializers.ValidationError({'password': 'La contraseña es requerida al crear un usuario.'})

        financiera_id = validated_data.pop('financiera_id')
        usuario = Usuario(
            **validated_data,
            financiera_id=financiera_id,
            full_name=validated_data['name'],
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        usuario.set_password(password)
        usuario.save()
        return usuario

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.updated_at = timezone.now()
        instance.save()
        return instance


class LoginSerializer(TokenObtainPairSerializer):
    """
    Extiende el serializer estándar de SimpleJWT para devolver también los
    datos del usuario autenticado (evita un segundo round-trip a /auth/me/).
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UsuarioSerializer(self.user).data
        return data
