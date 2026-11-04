-- Índices sugeridos para la base de la Intranet Inversa (MySQL/MariaDB).
--
-- NO se aplican desde Django: las tablas son del sistema anterior (`managed = False`) y el PHP sigue escribiendo en
-- ellas, así que un cambio de estructura lo decide y lo ejecuta quien administra la base, con respaldo previo y de
-- preferencia fuera de horario. Con los datos de hoy (decenas de filas por tabla) no hacen falta; se justifican
-- cuando `documentos` y `bitacora` lleguen a miles de filas.
--
-- Verificar antes y después con: EXPLAIN <consulta>. Revertir con: DROP INDEX <nombre> ON <tabla>;

-- Estados financieros: cada pantalla filtra por financiera y periodo. Hoy hay un índice suelto por columna
-- (anio, mes_id, id_corporacion, financiera_id) y el motor solo puede usar uno o combinarlos.
CREATE INDEX idx_documentos_financiera_periodo ON documentos (financiera_id, anio, mes_id, id_corporacion);

-- Campana de notificaciones y resumen del Dashboard: documentos pendientes, de los más recientes a los más antiguos.
CREATE INDEX idx_documentos_estado_fecha ON documentos (doc_aprobado, fecha);

-- Bitácora: la pantalla ordena por fecha y filtra por acción y rango de fechas; hoy solo tiene la clave primaria.
CREATE INDEX idx_bitacora_fecha ON bitacora (fecha);
CREATE INDEX idx_bitacora_accion_fecha ON bitacora (accion, fecha);

-- Documentos institucionales: la lista excluye los reemplazados y ordena por fecha de subida.
CREATE INDEX idx_upload_estado_fecha ON upload (estado, fecha);
