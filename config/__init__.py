import pymysql

# PyMySQL no requiere toolchain de compilación en Windows (a diferencia de
# mysqlclient), así que se usa como driver MySQL emulando la API de MySQLdb.
pymysql.install_as_MySQLdb()
pymysql.version_info = (1, 4, 6, 'final', 0)
