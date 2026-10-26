from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

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
