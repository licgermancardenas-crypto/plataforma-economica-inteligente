#!/usr/bin/env python3
"""
Inicializa la base SQLite y siembra el catálogo de indicadores/series validadas.
=================================================================================
Crea data/plataforma.db a partir de sql/schema.sql y carga:
  - fuentes de datos
  - los 6 indicadores núcleo
  - las series concretas con sus IDs canónicos (ver docs/fuentes_validadas.md)
  - banderas y reglas de calidad de datos

Es idempotente: se puede reejecutar (usa INSERT OR REPLACE en el catálogo).
NO ingiere observaciones — eso es la Etapa 3 (pipeline de ingesta).

Uso:
    python3 scripts/init_db.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "plataforma.db"
SCHEMA = ROOT / "sql" / "schema.sql"

# ---------------------------------------------------------------------------
# Catálogo (fuente de verdad del pipeline)
# ---------------------------------------------------------------------------
SOURCES = [
    ("bcra",           "Banco Central de la República Argentina (API v4.0)",
     "https://api.bcra.gob.ar/estadisticas/v4.0", "Monetarias. verify=False si falla SSL."),
    ("datosgob_series", "API Series de Tiempo del Estado (datos.gob.ar)",
     "https://apis.datos.gob.ar/series/api",
     "Infraestructura común: publican INDEC y la Secretaría de Hacienda (Min. Economía), "
     "entre otros. IDs canónicos por serie."),
    ("argentinadatos", "ArgentinaDatos (históricos financieros)",
     "https://api.argentinadatos.com/v1",
     "Dólar desde 2011 y riesgo país desde 1999. El external_id es el path bajo /v1."),
    ("dolarapi",       "dolarApi (cotización en tiempo real)",
     "https://dolarapi.com/v1", "Solo valor actual. Fallback tiempo real del TC."),
]

INDICATORS = [
    ("inflacion",    "Inflación (IPC)",              "precios",
     "Índice de precios al consumidor nacional, nivel general y núcleo."),
    ("tipo_cambio",  "Tipo de cambio y brecha",      "cambiario",
     "Cotizaciones oficial, MEP, CCL y blue; brecha respecto del oficial."),
    ("tasa",         "Tasa de referencia",           "monetario",
     "Tasa de referencia de mercado (TAMAR). Pases pasivos en 0 desde 2024/25."),
    ("actividad",    "Actividad económica (EMAE)",   "actividad",
     "Estimador Mensual de Actividad Económica, original y desestacionalizado."),
    ("monetario",    "Reservas y base monetaria",    "monetario",
     "Reservas internacionales del BCRA y base monetaria."),
    ("empleo",       "Mercado laboral (EPH)",        "empleo",
     "Tasa de desocupación nacional (EPH, trimestral)."),
    ("externo",      "Sector externo (comercio)",    "externo",
     "Exportaciones e importaciones totales (INDEC). El saldo comercial se deriva."),
    ("riesgo",       "Riesgo soberano",              "financiero",
     "Riesgo país (EMBI+ Argentina), diario desde 1999."),
    ("fiscal",       "Resultado fiscal y recaudación", "fiscal",
     "Sector Público Nacional no financiero: resultado primario, intereses, resultado "
     "financiero y recaudación. Secretaría de Hacienda (Ministerio de Economía)."),
]

# series_id, indicator, source, external_id, name, unit, freq, sa, kind, scale, base, notes
SERIES = [
    ("ipc_general",   "inflacion",   "datosgob_series", "148.3_INIVELNAL_DICI_M_26",
     "IPC Nivel General Nacional", "índice dic-2016=100", "M", "none", "index", 1.0, "dic-2016", None),
    ("ipc_nucleo",    "inflacion",   "datosgob_series", "148.3_INUCLEONAL_DICI_M_19",
     "IPC Núcleo Nacional", "índice dic-2016=100", "M", "none", "index", 1.0, "dic-2016",
     "Aísla ruido de regulados/estacionales."),

    ("usd_oficial",   "tipo_cambio", "argentinadatos", "cotizaciones/dolares/oficial",
     "Dólar oficial (venta)", "ARS/USD", "D", "none", "level", 1.0, None, "Histórico desde 2011."),
    ("usd_mep",       "tipo_cambio", "argentinadatos", "cotizaciones/dolares/bolsa",
     "Dólar MEP/Bolsa (venta)", "ARS/USD", "D", "none", "level", 1.0, None, None),
    ("usd_ccl",       "tipo_cambio", "argentinadatos", "cotizaciones/dolares/contadoconliqui",
     "Dólar CCL (venta)", "ARS/USD", "D", "none", "level", 1.0, None, None),
    ("usd_blue",      "tipo_cambio", "argentinadatos", "cotizaciones/dolares/blue",
     "Dólar blue (venta)", "ARS/USD", "D", "none", "level", 1.0, None, None),
    ("tc_mayorista",  "tipo_cambio", "bcra", "5",
     "Tipo de cambio mayorista de referencia", "ARS/USD", "D", "none", "level", 1.0, None,
     "TC oficial de referencia BCRA; base para TC real."),

    ("tamar_priv",    "tasa",        "bcra", "44",
     "TAMAR bancos privados (TNA)", "% nominal anual", "D", "none", "rate", 1.0, None,
     "Proxy de tasa de referencia. REVISAR según régimen monetario."),

    ("emae_original", "actividad",   "datosgob_series", "143.3_NO_PR_2004_A_21",
     "EMAE serie original", "índice 2004=100", "M", "none", "index", 1.0, "2004", None),
    ("emae_desest",   "actividad",   "datosgob_series", "302.3_S_DESEST_NRAL_0_S_19",
     "EMAE desestacionalizada", "índice 2004=100", "M", "sa", "index", 1.0, "2004",
     "Desestacionalización oficial INDEC."),

    ("reservas",      "monetario",   "bcra", "1",
     "Reservas internacionales", "millones USD", "D", "none", "level", 1.0, None, None),
    ("base_monetaria","monetario",   "bcra", "15",
     "Base monetaria", "millones ARS", "D", "none", "level", 1.0, None, None),

    ("desempleo",     "empleo",      "datosgob_series", "42.3_EPH_PUNTUATAL_0_M_30",
     "Tasa de desocupación nacional", "%", "Q", "none", "rate", 100.0, None,
     "Fuente devuelve fracción (0.078); scale=100 la normaliza a 7.8."),

    # Bloque fiscal — Secretaría de Hacienda (Min. Economía) vía Series de Tiempo.
    # IMIG = Informe Mensual de Ingresos y Gastos del SPN. Flujos MENSUALES (no acumulados)
    # en pesos NOMINALES: hay que deflactar por IPC (o expresar en % del EMAE) antes de
    # estimar nada — en niveles nominales un VAR captura inflación, no política fiscal.
    ("resultado_primario",   "fiscal", "datosgob_series", "452.3_RESULTADO_RIO_0_M_18_54",
     "Resultado primario SPN (IMIG)", "millones ARS", "M", "none", "level", 1.0, None,
     "Ingresos totales menos gastos primarios. Identidad: primario - intereses = financiero."),
    ("intereses_netos",      "fiscal", "datosgob_series", "452.3_INTERESES_TOS_0_M_15_62",
     "Intereses netos SPN (IMIG)", "millones ARS", "M", "none", "level", 1.0, None,
     "Intereses de deuda netos de intra-sector público."),
    ("resultado_financiero", "fiscal", "datosgob_series", "452.3_RESULTADO_ERO_0_M_20_25",
     "Resultado financiero SPN (IMIG)", "millones ARS", "M", "none", "level", 1.0, None,
     "COLINEAL con primario+intereses (identidad exacta): en un VAR va ESTA o aquellas dos, "
     "nunca las tres."),
    ("recaudacion_total",    "fiscal", "datosgob_series", "172.3_TL_RECAION_M_0_0_17",
     "Recaudación tributaria total", "millones ARS", "M", "none", "level", 1.0, None,
     "Desde 1997: mucho más larga que el IMIG (2016+) y se publica antes."),

    # Sector externo — INDEC vía Series de Tiempo. X y M van por separado: el saldo
    # comercial es una resta y se calcula al analizar, no se persiste (mismo criterio
    # que el remuestreo, cf. sql/schema.sql). Además la serie oficial de saldo
    # (164.3_SOTALTAL_0_0_8) está congelada en 2025-02, mientras X y M llegan a 2026-06.
    ("exportaciones", "externo", "datosgob_series", "74.3_IET_0_M_16",
     "Exportaciones totales", "millones USD", "M", "none", "level", 1.0, None, None),
    ("importaciones", "externo", "datosgob_series", "74.3_IIT_0_M_25",
     "Importaciones totales", "millones USD", "M", "none", "level", 1.0, None, None),

    ("riesgo_pais",   "riesgo",  "argentinadatos", "finanzas/indices/riesgo-pais",
     "Riesgo país (EMBI+ Argentina)", "puntos básicos", "D", "none", "level", 1.0, None,
     "Única serie de la base que cubre 2001, 2018 y 2019: sirve para identificar "
     "quiebres estructurales fuera de la muestra corta post-2016."),
]

QUALITY_FLAGS = [
    ("OK",          "Dato oficial definitivo sin observaciones."),
    ("PROVISORIO",  "Dato sujeto a revisión oficial."),
    ("INTERVENIDO", "Período de intervención del organismo (calidad estadística comprometida)."),
    ("REBASE",      "Cambio de base/empalme que puede afectar comparabilidad."),
    ("ESTIMADO",    "Valor estimado/imputado, no observado directamente."),
]

# Reglas de calidad conocidas. La serie IPC nacional vigente arranca en dic-2016
# (post-intervención), así que esta regla no marcará datos hoy; queda documentada
# para el día que se empalme una serie larga de IPC hacia atrás.
QUALITY_PERIODS = [
    ("inflacion", None, "2007-01-01", "2015-12-01", "INTERVENIDO",
     "IPC-GBA bajo intervención del INDEC; no usar para inferencia sin ajuste."),
]


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))

    con.executemany("INSERT OR REPLACE INTO sources VALUES (?,?,?,?)", SOURCES)
    con.executemany("INSERT OR REPLACE INTO indicators VALUES (?,?,?,?)", INDICATORS)
    con.executemany(
        "INSERT OR REPLACE INTO series "
        "(series_id,indicator_id,source_id,external_id,name,unit,frequency,"
        " seasonal_adj,kind,scale,base_period,notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", SERIES)
    # Las series ya apuntan al catálogo nuevo: purgar fuentes/indicadores que salieron
    # de él (el rename indec_datosgob -> datosgob_series sobre una base ya creada).
    con.execute(f"DELETE FROM sources WHERE source_id NOT IN ({','.join('?' * len(SOURCES))})",
                [s[0] for s in SOURCES])
    con.execute(f"DELETE FROM indicators WHERE indicator_id NOT IN "
                f"({','.join('?' * len(INDICATORS))})", [i[0] for i in INDICATORS])

    con.executemany("INSERT OR REPLACE INTO quality_flags VALUES (?,?)", QUALITY_FLAGS)
    # quality_periods no tiene clave natural; limpiamos y recargamos para idempotencia
    con.execute("DELETE FROM quality_periods")
    con.executemany(
        "INSERT INTO quality_periods "
        "(indicator_id,series_id,date_from,date_to,flag_code,note) VALUES (?,?,?,?,?,?)",
        QUALITY_PERIODS)
    con.commit()

    # Verificación
    print(f"Base creada en: {DB_PATH}")
    for tabla in ("sources", "indicators", "series", "quality_flags", "quality_periods"):
        n = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        print(f"  {tabla:16} {n} filas")
    print("\nSeries por indicador:")
    for ind, cnt in con.execute(
        "SELECT indicator_id, COUNT(*) FROM series GROUP BY indicator_id ORDER BY indicator_id"):
        print(f"  {ind:14} {cnt}")
    con.close()


if __name__ == "__main__":
    main()
