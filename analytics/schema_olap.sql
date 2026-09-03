-- =====================================================================
-- Esquema ANALITICO (OLAP) - Sistema de reservas aereas
-- Modelo ESTRELLA. Responde las 3 preguntas de negocio del enunciado:
--   1. Ocupacion por ruta
--   2. Ingresos por tarifa
--   3. Patrones de cancelacion
--
-- Se puebla desde el OLTP (docs/03) mediante el ETL de etl/etl.py.
-- El esquema NO es identico al transaccional (justificacion en docs/07 5.7.2):
--   OLTP en 3FN (evita anomalias en escritura) vs OLAP desnormalizado
--   (menos joins, consultas analiticas rapidas).
-- =====================================================================

DROP TABLE IF EXISTS fact_reserva_segmento CASCADE;
DROP TABLE IF EXISTS dim_tiempo CASCADE;
DROP TABLE IF EXISTS dim_ruta CASCADE;
DROP TABLE IF EXISTS dim_vuelo CASCADE;
DROP TABLE IF EXISTS dim_tarifa CASCADE;
DROP TABLE IF EXISTS dim_canal CASCADE;

-- ---------------------------------------------------------------------
-- DIMENSIONES
-- ---------------------------------------------------------------------

CREATE TABLE dim_tiempo (
    id_tiempo        INTEGER PRIMARY KEY,          -- AAAAMMDD
    fecha            DATE NOT NULL,
    anio             SMALLINT NOT NULL,
    mes              SMALLINT NOT NULL,
    dia              SMALLINT NOT NULL,
    dia_semana       SMALLINT NOT NULL,            -- 1=lun ... 7=dom
    nombre_mes       VARCHAR(12) NOT NULL,
    es_fin_semana    BOOLEAN NOT NULL,
    temporada        VARCHAR(10) NOT NULL          -- ALTA / BAJA (derivada del mes)
);

CREATE TABLE dim_ruta (
    id_ruta          BIGINT PRIMARY KEY,           -- = ruta.id_ruta del OLTP
    iata_origen      CHAR(3) NOT NULL,
    iata_destino     CHAR(3) NOT NULL,
    ciudad_origen    VARCHAR(80) NOT NULL,
    ciudad_destino   VARCHAR(80) NOT NULL,
    par_ruta         VARCHAR(7) NOT NULL,          -- 'BOG-MDE'
    distancia_km     INTEGER
);

CREATE TABLE dim_vuelo (
    id_instancia_vuelo BIGINT PRIMARY KEY,         -- = instancia_vuelo.id_instancia_vuelo
    numero_vuelo       VARCHAR(6) NOT NULL,
    fecha_salida       DATE NOT NULL,
    modelo_aeronave    VARCHAR(40) NOT NULL,
    asientos_totales   SMALLINT NOT NULL,          -- capacidad de la aeronave (todas las cabinas)
    estado             VARCHAR(12) NOT NULL
);

CREATE TABLE dim_tarifa (
    id_tarifa        BIGINT PRIMARY KEY,           -- = tarifa.id_tarifa del OLTP
    clase_tarifa     VARCHAR(20) NOT NULL,         -- PROMO / FLEX / BUSINESS
    cabina           VARCHAR(10) NOT NULL,         -- ECONOMICA / EJECUTIVA
    es_reembolsable  BOOLEAN NOT NULL,
    ventana_compra   VARCHAR(20) NOT NULL          -- 'anticipada' / 'ultima hora' (derivada)
);

CREATE TABLE dim_canal (
    id_canal         SMALLINT PRIMARY KEY,
    canal            VARCHAR(10) NOT NULL,         -- DIRECTO / AGENCIA
    descripcion      VARCHAR(60) NOT NULL
);

INSERT INTO dim_canal (id_canal, canal, descripcion) VALUES
    (1, 'DIRECTO', 'Venta directa en el sitio web de la aerolinea'),
    (2, 'AGENCIA', 'Venta a traves de agencia de viajes asociada');

-- ---------------------------------------------------------------------
-- HECHO
-- Grano: UN segmento de reserva (un pasajero-tramo tiene 1 fila por
-- pasajero? -> NO: el grano es el segmento; num_pasajeros es una medida).
-- Elegido asi porque las 3 preguntas de negocio se responden a nivel
-- de tramo-vuelo (ocupacion por ruta, ingreso por tarifa, cancelaciones).
-- ---------------------------------------------------------------------

CREATE TABLE fact_reserva_segmento (
    id_fact              BIGSERIAL PRIMARY KEY,

    -- claves de dimension
    id_tiempo_reserva    INTEGER NOT NULL REFERENCES dim_tiempo(id_tiempo),
    id_tiempo_vuelo      INTEGER NOT NULL REFERENCES dim_tiempo(id_tiempo),
    id_ruta              BIGINT  NOT NULL REFERENCES dim_ruta(id_ruta),
    id_instancia_vuelo   BIGINT  NOT NULL REFERENCES dim_vuelo(id_instancia_vuelo),
    id_tarifa            BIGINT  NOT NULL REFERENCES dim_tarifa(id_tarifa),
    id_canal             SMALLINT NOT NULL REFERENCES dim_canal(id_canal),

    -- degeneradas (identifican el hecho en el origen, sin dimension propia)
    codigo_reserva       CHAR(6) NOT NULL,
    id_segmento_itinerario BIGINT NOT NULL,

    -- medidas
    num_pasajeros        SMALLINT NOT NULL,
    ingreso_segmento     NUMERIC(14,2) NOT NULL,   -- monto del tramo (ya con descuento de agencia prorrateado)
    comision_agencia     NUMERIC(14,2) NOT NULL DEFAULT 0,
    asientos_cabina      SMALLINT NOT NULL,        -- capacidad de la cabina comprada (para % ocupacion)

    -- banderas de estado (para patrones de cancelacion)
    estado_reserva       VARCHAR(12) NOT NULL,     -- RETENIDA/CONFIRMADA/CANCELADA/EXPIRADA
    es_confirmada        BOOLEAN NOT NULL,
    es_cancelada         BOOLEAN NOT NULL,
    es_expirada          BOOLEAN NOT NULL,

    fecha_carga_etl      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (id_segmento_itinerario)   -- idempotencia del ETL (upsert por segmento)
);

CREATE INDEX ix_fact_ruta       ON fact_reserva_segmento (id_ruta);
CREATE INDEX ix_fact_tarifa     ON fact_reserva_segmento (id_tarifa);
CREATE INDEX ix_fact_vuelo      ON fact_reserva_segmento (id_instancia_vuelo);
CREATE INDEX ix_fact_t_vuelo    ON fact_reserva_segmento (id_tiempo_vuelo);

-- =====================================================================
-- VISTAS DE NEGOCIO (las 3 preguntas del enunciado)
-- =====================================================================

-- 1. OCUPACION POR RUTA (solo reservas confirmadas cuentan como ocupacion)
--    La capacidad se calcula por vuelo distinto (sub-consulta) para no inflar
--    el denominador con la repeticion de filas del hecho.
CREATE OR REPLACE VIEW v_ocupacion_por_ruta AS
WITH pax AS (
    SELECT f.id_ruta, f.id_tiempo_vuelo, f.id_instancia_vuelo,
           SUM(f.num_pasajeros) FILTER (WHERE f.es_confirmada) AS pax_confirmados
    FROM fact_reserva_segmento f
    GROUP BY f.id_ruta, f.id_tiempo_vuelo, f.id_instancia_vuelo
),
cap AS (
    SELECT DISTINCT f.id_instancia_vuelo, v.asientos_totales
    FROM fact_reserva_segmento f
    JOIN dim_vuelo v ON v.id_instancia_vuelo = f.id_instancia_vuelo
)
SELECT
    r.par_ruta,
    r.ciudad_origen,
    r.ciudad_destino,
    t.anio,
    t.mes,
    t.temporada,
    COALESCE(SUM(p.pax_confirmados), 0)                    AS pasajeros_confirmados,
    COUNT(DISTINCT p.id_instancia_vuelo)                   AS vuelos,
    SUM(c.asientos_totales)                                AS asientos_ofertados,
    ROUND(100.0 * COALESCE(SUM(p.pax_confirmados),0)
          / NULLIF(SUM(c.asientos_totales),0), 1)          AS pct_ocupacion
FROM pax p
JOIN cap c      ON c.id_instancia_vuelo = p.id_instancia_vuelo
JOIN dim_ruta r ON r.id_ruta = p.id_ruta
JOIN dim_tiempo t ON t.id_tiempo = p.id_tiempo_vuelo
GROUP BY r.par_ruta, r.ciudad_origen, r.ciudad_destino, t.anio, t.mes, t.temporada;

-- 2. INGRESOS POR TARIFA
CREATE OR REPLACE VIEW v_ingresos_por_tarifa AS
SELECT
    d.clase_tarifa,
    d.cabina,
    d.ventana_compra,
    t.anio,
    t.mes,
    SUM(f.ingreso_segmento) FILTER (WHERE f.es_confirmada)     AS ingreso_confirmado,
    SUM(f.comision_agencia) FILTER (WHERE f.es_confirmada)     AS comision_pagada,
    SUM(f.num_pasajeros)    FILTER (WHERE f.es_confirmada)     AS pasajeros,
    ROUND(
        SUM(f.ingreso_segmento) FILTER (WHERE f.es_confirmada)
        / NULLIF(SUM(f.num_pasajeros) FILTER (WHERE f.es_confirmada),0), 2) AS ingreso_promedio_pax
FROM fact_reserva_segmento f
JOIN dim_tarifa d ON d.id_tarifa = f.id_tarifa
JOIN dim_tiempo t ON t.id_tiempo = f.id_tiempo_reserva
GROUP BY d.clase_tarifa, d.cabina, d.ventana_compra, t.anio, t.mes;

-- 3. PATRONES DE CANCELACION
CREATE OR REPLACE VIEW v_patrones_cancelacion AS
SELECT
    r.par_ruta,
    d.clase_tarifa,
    dc.canal,
    t.anio,
    t.mes,
    t.temporada,
    COUNT(*)                                                   AS segmentos_totales,
    COUNT(*) FILTER (WHERE f.es_cancelada)                     AS segmentos_cancelados,
    COUNT(*) FILTER (WHERE f.es_expirada)                      AS segmentos_expirados,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.es_cancelada) / NULLIF(COUNT(*),0), 1) AS pct_cancelacion,
    SUM(f.ingreso_segmento) FILTER (WHERE f.es_cancelada)      AS ingreso_perdido_cancelaciones
FROM fact_reserva_segmento f
JOIN dim_ruta   r  ON r.id_ruta = f.id_ruta
JOIN dim_tarifa d  ON d.id_tarifa = f.id_tarifa
JOIN dim_canal  dc ON dc.id_canal = f.id_canal
JOIN dim_tiempo t  ON t.id_tiempo = f.id_tiempo_reserva
GROUP BY r.par_ruta, d.clase_tarifa, dc.canal, t.anio, t.mes, t.temporada;
