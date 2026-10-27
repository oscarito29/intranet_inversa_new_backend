from apps.usuarios.models import Usuario


def usuario_puede_ver_financiera(usuario: Usuario, financiera_id: str) -> bool:
    """
    Control de acceso real (en el servidor) a documentos de una financiera.
    En el legado esto SOLO se validaba en JavaScript; aquí se aplica siempre,
    sin importar lo que pida el cliente.
    """
    if usuario.rol_id == 1:
        return True
    return str(usuario.financiera_id) == str(financiera_id)
