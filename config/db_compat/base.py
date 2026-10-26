"""
Backend MySQL para DESARROLLO LOCAL únicamente.

El MariaDB local del equipo es 10.1.38 (EOL desde 2020); Django 5.2 exige
MariaDB >= 10.5 o MySQL >= 8.0.11 y aborta la conexión si no lo detecta.
Producción corre MySQL 8.0.44 (sí soportado), así que este shim no se usa ahí
-- ver config/settings/production.py, que sigue usando django.db.backends.mysql.

TODO: si se actualiza el MariaDB local a 10.5+, eliminar este archivo y volver
a ENGINE = 'django.db.backends.mysql' en config/settings/development.py.
"""

from django.db.backends.mysql.base import DatabaseWrapper as MySQLDatabaseWrapper
from django.db.backends.mysql.features import DatabaseFeatures as MySQLDatabaseFeatures


class DatabaseFeatures(MySQLDatabaseFeatures):
    # MariaDB 10.1 no soporta `INSERT ... RETURNING` (eso llegó en 10.5).
    can_return_columns_from_insert = False
    can_return_rows_from_bulk_insert = False


class DatabaseWrapper(MySQLDatabaseWrapper):
    features_class = DatabaseFeatures

    def check_database_version_supported(self) -> None:
        pass
