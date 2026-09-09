-- ============================================================================
-- Plataforma Económica Inteligente — Esquema de almacenamiento (SQLite)
-- ============================================================================
-- Principios de diseño (objetivo: herramienta de análisis con econometría):
--   1. Cada serie se guarda en su FRECUENCIA NATIVA (D/M/Q). El remuestreo a
--      frecuencia común para VAR/VECM/Granger se hace en pandas al analizar,
--      no se persiste.
--   2. observations.value guarda el valor YA NORMALIZADO (crudo * series.scale),
--      para que el desempleo (0.078) se almacene como 7.8 y todo sea homogéneo.
--   3. La calidad de datos es de primera clase: quality_flags + quality_periods
--      permiten marcar tramos no confiables (INDEC intervenido, provisorios,
--      rebases) sin borrar datos ni contaminar los modelos.
-- ----------------------------------------------------------------------------

PRAGMA foreign_keys = ON;

-- Fuentes de datos ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    source_id  TEXT PRIMARY KEY,          -- slug: bcra, indec_datosgob, argentinadatos
    name       TEXT NOT NULL,
    base_url   TEXT,
    notes      TEXT
);

-- Indicadores conceptuales (los 6 núcleo del documento) -----------------------
CREATE TABLE IF NOT EXISTS indicators (
    indicator_id TEXT PRIMARY KEY,        -- slug: inflacion, tipo_cambio, ...
    name         TEXT NOT NULL,
    category     TEXT,                     -- precios, monetario, cambiario, actividad, externo, empleo
    description  TEXT
);

-- Catálogo de series concretas (un indicador puede tener varias) ---------------
CREATE TABLE IF NOT EXISTS series (
    series_id    TEXT PRIMARY KEY,        -- slug: ipc_general, usd_ccl, emae_desest
    indicator_id TEXT NOT NULL REFERENCES indicators(indicator_id),
    source_id    TEXT NOT NULL REFERENCES sources(source_id),
    external_id  TEXT,                     -- id en la API de origen
    name         TEXT NOT NULL,
    unit         TEXT,                     -- 'índice dic-2016=100', 'ARS/USD', '% n.a.', '%'
    frequency    TEXT NOT NULL CHECK (frequency IN ('D','M','Q')),
    seasonal_adj TEXT NOT NULL DEFAULT 'none' CHECK (seasonal_adj IN ('none','sa')),
    kind         TEXT NOT NULL DEFAULT 'level' CHECK (kind IN ('level','index','rate','ratio')),
    scale        REAL NOT NULL DEFAULT 1.0, -- multiplicador de normalización (100 para desempleo)
    base_period  TEXT,                      -- 'dic-2016', '2004', NULL
    active       INTEGER NOT NULL DEFAULT 1,
    notes        TEXT
);

-- Catálogo de banderas de calidad ---------------------------------------------
CREATE TABLE IF NOT EXISTS quality_flags (
    flag_code   TEXT PRIMARY KEY,         -- OK, PROVISIONAL, INTERVENIDO, REBASE, ESTIMADO
    description TEXT NOT NULL
);

-- Observaciones (el dato en sí) -----------------------------------------------
-- obs_date = primer día del período (para M/Q se usa el 1º del mes/trimestre).
CREATE TABLE IF NOT EXISTS observations (
    series_id    TEXT NOT NULL REFERENCES series(series_id),
    obs_date     TEXT NOT NULL,           -- ISO 'YYYY-MM-DD'
    value        REAL,                    -- normalizado (crudo * series.scale)
    quality_flag TEXT NOT NULL DEFAULT 'OK' REFERENCES quality_flags(flag_code),
    ingested_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    PRIMARY KEY (series_id, obs_date)
);

-- Reglas de calidad por ventana temporal --------------------------------------
-- Se materializan sobre observations.quality_flag al ingerir. Si series_id es
-- NULL, la regla aplica a todas las series del indicator_id.
CREATE TABLE IF NOT EXISTS quality_periods (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_id TEXT REFERENCES indicators(indicator_id),
    series_id    TEXT REFERENCES series(series_id),
    date_from    TEXT NOT NULL,           -- ISO
    date_to      TEXT,                    -- ISO o NULL (abierto)
    flag_code    TEXT NOT NULL REFERENCES quality_flags(flag_code),
    note         TEXT
);

CREATE INDEX IF NOT EXISTS idx_obs_date        ON observations(obs_date);
CREATE INDEX IF NOT EXISTS idx_series_indicator ON series(indicator_id);

-- Vista de conveniencia: última observación por serie -------------------------
CREATE VIEW IF NOT EXISTS v_ultimo_dato AS
SELECT o.series_id, s.name AS serie, s.unit, o.obs_date, o.value, o.quality_flag
FROM observations o
JOIN series s ON s.series_id = o.series_id
JOIN (SELECT series_id, MAX(obs_date) AS md FROM observations GROUP BY series_id) m
  ON m.series_id = o.series_id AND m.md = o.obs_date;

-- ============================================================================
-- Comercio espejo (mirror trade) — flujos financieros ilícitos vía facturación
-- ============================================================================
-- POR QUÉ UNA TABLA APARTE Y NO SERIES. `observations` es (series_id, obs_date):
-- una serie de tiempo univariada. Esto es un PANEL de cuatro dimensiones
-- (año × quién declara × contraparte × flujo). Meterlo en `series` obligaría a
-- inventar cientos de series_id sintéticos y, sobre todo, haría inexpresable el
-- apareo espejo —comparar lo que A declara exportar a B contra lo que B declara
-- importar de A—, que es justamente la operación por la que existe esta tabla.
--
-- Se guarda CRUDO, tal como lo reporta cada país. La discrepancia, el ajuste
-- CIF/FOB y la agregación se derivan en `platec.comercio_espejo`, mismo criterio
-- que el saldo comercial y el remuestreo: las transformaciones van en pandas,
-- no en la base.
--
-- primary_value es la valoración primaria del reportante (FOB en exportaciones,
-- CIF en importaciones, según la convención de Comtrade). fob_value y cif_value
-- vienen SEPARADOS y pueden ser NULL: solo una minoría de los países informa las
-- dos valoraciones, y esa diferencia es el flete y el seguro, no una anomalía.
CREATE TABLE IF NOT EXISTS trade_mirror (
    year          INTEGER NOT NULL,
    reporter_code INTEGER NOT NULL,       -- M49 del país que declara
    partner_code  INTEGER NOT NULL,       -- M49 de la contraparte (0 = Mundo)
    flow_code     TEXT NOT NULL CHECK (flow_code IN ('X','M')),
    primary_value REAL,                   -- valoración primaria del reportante
    fob_value     REAL,                   -- NULL si el reportante no la informa
    cif_value     REAL,                   -- NULL si el reportante no la informa
    ingested_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    PRIMARY KEY (year, reporter_code, partner_code, flow_code)
);

CREATE INDEX IF NOT EXISTS idx_mirror_year    ON trade_mirror(year);
CREATE INDEX IF NOT EXISTS idx_mirror_partner ON trade_mirror(partner_code, flow_code);
