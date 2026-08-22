#!/usr/bin/env python3
"""
Pipeline de ingesta — Plataforma Económica Inteligente (Etapa 3)
================================================================
Puebla la tabla `observations` descargando el histórico de cada serie activa
del catálogo (`series`) desde su API de origen, normalizando el valor
(crudo * series.scale) y aplicando las banderas de calidad de `quality_periods`.

Tres patrones de fuente:
  - datosgob_series : GET /series?ids=... (una request, orden ascendente)
  - bcra           : GET /Monetarias/{id} paginado por offset (orden descendente)
  - argentinadatos : GET /{path} (el external_id ES el path; histórico completo)
  - dolarapi       : se omite (solo valor actual; es fallback tiempo real)

Idempotente: usa INSERT OR REPLACE sobre (series_id, obs_date), así que se puede
reejecutar para actualizar sin duplicar.

Uso:
    python3 scripts/ingest.py                 # todas las series activas
    python3 scripts/ingest.py ipc_general tc_mayorista   # solo algunas
"""
from __future__ import annotations

import sqlite3
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import requests

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "plataforma.db"
TIMEOUT = 40
UA = {"User-Agent": "plataforma-economica/0.1"}

BCRA_BASE = "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias"
DATOSGOB_BASE = "https://apis.datos.gob.ar/series/api/series"
ARGDATOS_BASE = "https://api.argentinadatos.com/v1"


# ---------------------------------------------------------------------------
# Fetchers: devuelven lista de (obs_date 'YYYY-MM-DD', valor_crudo float)
# ---------------------------------------------------------------------------
def fetch_datosgob(external_id: str) -> list[tuple[str, float]]:
    url = f"{DATOSGOB_BASE}?ids={external_id}&format=json&limit=5000"
    j = requests.get(url, headers=UA, timeout=TIMEOUT).json()
    if "errors" in j:
        raise RuntimeError(f"datos.gob.ar: {j['errors']}")
    out = []
    for row in j.get("data", []):
        fecha, valor = row[0], row[1]
        if valor is not None:
            out.append((fecha[:10], float(valor)))
    return out


def fetch_bcra(external_id: str) -> list[tuple[str, float]]:
    limit, offset, out = 3000, 0, []
    while True:
        url = (f"{BCRA_BASE}/{external_id}"
               f"?desde=1990-01-01&hasta=2100-01-01&limit={limit}&offset={offset}")
        j = requests.get(url, headers=UA, timeout=TIMEOUT, verify=False).json()
        res = j.get("results", [])
        det = res[0].get("detalle", []) if res and isinstance(res[0], dict) else res
        for d in det:
            v = d.get("valor")
            if v is not None:
                out.append((d["fecha"][:10], float(v)))
        count = j.get("metadata", {}).get("resultset", {}).get("count", len(det))
        offset += limit
        if offset >= count or not det:
            break
    return out


def fetch_argentinadatos(external_id: str) -> list[tuple[str, float]]:
    """
    external_id es el PATH bajo /v1 ('cotizaciones/dolares/blue',
    'finanzas/indices/riesgo-pais'), porque la API sirve familias distintas bajo
    la misma base. El campo del valor cambia con la familia: las cotizaciones
    traen 'venta' y los índices traen 'valor'.
    """
    url = f"{ARGDATOS_BASE}/{external_id}"
    j = requests.get(url, headers=UA, timeout=TIMEOUT).json()
    out = []
    for d in j:
        v = d["venta"] if "venta" in d else d.get("valor")
        if v is not None:
            out.append((d["fecha"][:10], float(v)))
    return out


FETCHERS = {
    "datosgob_series": fetch_datosgob,
    "bcra": fetch_bcra,
    "argentinadatos": fetch_argentinadatos,
}


# ---------------------------------------------------------------------------
# Calidad
# ---------------------------------------------------------------------------
def cargar_reglas_calidad(con) -> list[dict]:
    cols = ["indicator_id", "series_id", "date_from", "date_to", "flag_code"]
    return [dict(zip(cols, r)) for r in con.execute(
        "SELECT indicator_id, series_id, date_from, date_to, flag_code FROM quality_periods")]


def flag_para(reglas, series_id, indicator_id, obs_date) -> str:
    for r in reglas:
        aplica_serie = (r["series_id"] == series_id) or \
                       (r["series_id"] is None and r["indicator_id"] == indicator_id)
        if not aplica_serie:
            continue
        if r["date_from"] <= obs_date and (r["date_to"] is None or obs_date <= r["date_to"]):
            return r["flag_code"]
    return "OK"


# ---------------------------------------------------------------------------
# Ingesta
# ---------------------------------------------------------------------------
def ingerir_serie(con, s: dict, reglas) -> tuple[int, str]:
    fetcher = FETCHERS.get(s["source_id"])
    if fetcher is None:
        return 0, f"fuente '{s['source_id']}' sin fetcher (omitida)"
    crudos = fetcher(s["external_id"])
    scale = s["scale"]
    filas = []
    for fecha, valor in crudos:
        flag = flag_para(reglas, s["series_id"], s["indicator_id"], fecha)
        filas.append((s["series_id"], fecha, valor * scale, flag))
    con.executemany(
        "INSERT OR REPLACE INTO observations (series_id, obs_date, value, quality_flag) "
        "VALUES (?,?,?,?)", filas)
    con.commit()
    rango = f"{crudos[-1][0]}..{crudos[0][0]}" if crudos else "—"
    # crudos puede venir asc o desc; calculamos min/max real
    if crudos:
        fechas = [f for f, _ in crudos]
        rango = f"{min(fechas)}..{max(fechas)}"
    return len(filas), rango


def main(argv):
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    con.row_factory = sqlite3.Row

    q = "SELECT * FROM series WHERE active = 1"
    params = ()
    if argv:
        q += f" AND series_id IN ({','.join('?' * len(argv))})"
        params = tuple(argv)
    series = [dict(r) for r in con.execute(q, params)]
    reglas = cargar_reglas_calidad(con)

    print("=" * 72)
    print(f"INGESTA — {datetime.now(timezone.utc).isoformat()}  ({len(series)} series)")
    print("=" * 72)
    total = 0
    for s in series:
        try:
            n, rango = ingerir_serie(con, s, reglas)
            total += n
            print(f"  \033[92m✓\033[0m {s['series_id']:16} {n:6} obs  [{rango}]  ({s['source_id']})")
        except Exception as e:
            print(f"  \033[91m✗\033[0m {s['series_id']:16} ERROR: {type(e).__name__}: {e}")

    print("-" * 72)
    print(f"Total observaciones ingeridas/actualizadas: {total}")
    # Marcadas por calidad distinta de OK
    marcadas = con.execute(
        "SELECT quality_flag, COUNT(*) FROM observations WHERE quality_flag <> 'OK' "
        "GROUP BY quality_flag").fetchall()
    if marcadas:
        print("Observaciones con bandera de calidad:",
              {r[0]: r[1] for r in marcadas})
    con.close()


if __name__ == "__main__":
    main(sys.argv[1:])
