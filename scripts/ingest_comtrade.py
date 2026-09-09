#!/usr/bin/env python3
"""
Ingesta de comercio espejo (UN Comtrade) — puebla `trade_mirror`.
==================================================================
Descarga, por año, los dos lados de cada relación comercial de Argentina:

  lado A  reporter = Argentina, partner = todos   -> lo que ARGENTINA declara
  lado B  reporter = todos,     partner = Argentina -> lo que EL SOCIO declara

Con los dos lados se puede aparear el espejo: lo que Argentina dice haber
exportado a Brasil contra lo que Brasil dice haber importado de Argentina. La
diferencia entre ambos, una vez descontados flete y seguro, es el insumo de la
literatura de flujos financieros ilícitos por mala facturación comercial.

POR QUÉ `requests` Y NO EL PAQUETE `comtradeapicall`. El paquete oficial envuelve
este mismo endpoint REST; sus funciones que agregan valor de verdad
(`getBilateralData`, `getFinalData`) exigen subscription key de pago. Lo que acá
se usa —`/public/v1/preview`— es gratis y sin credenciales, y son treinta líneas.
Sumar una dependencia (que además arrastra sus propias versiones de pandas) al
build de Streamlit Cloud para eso no se paga. Los otros tres fetchers del
proyecto (BCRA, datos.gob.ar, argentinadatos) están escritos igual.

LÍMITES DEL ENDPOINT GRATUITO, medidos contra la API real (2026-09):
  - Un solo período por llamada. `period=2015,2016` devuelve 400.
  - Techo de 500 registros por respuesta. Argentina contra todos los socios,
    un año, ambos flujos, da ~350: entra, pero con poco aire. Si alguna vez se
    baja a nivel de capítulo HS esto explota y hay que paginar o pagar la key.
    El ingestor avisa si una respuesta llega al techo en vez de truncar callado.

Idempotente: INSERT OR REPLACE sobre (year, reporter, partner, flow).

Uso:
    python3 scripts/ingest_comtrade.py                 # 1995 -> último disponible
    python3 scripts/ingest_comtrade.py 2015 2025       # rango explícito
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "plataforma.db"

BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
UA = {"User-Agent": "plataforma-economica/0.1"}
TIMEOUT = 90

ARGENTINA = 32          # código M49
DESDE_DEFECTO = 1995
TECHO_PREVIEW = 500     # registros por respuesta del endpoint gratuito
PAUSA = 1.5             # segundos entre llamadas; la API no publica su rate limit


def _pedir(**params) -> list[dict]:
    """Una consulta al preview público. Devuelve las filas de `data`."""
    p = {"cmdCode": "TOTAL", "partner2Code": 0, "customsCode": "C00", "motCode": 0}
    p.update(params)
    r = requests.get(BASE, params=p, headers=UA, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"comtrade {r.status_code}: {r.text[:200]}")
    j = r.json()
    if j.get("error"):
        raise RuntimeError(f"comtrade: {j['error']}")
    datos = j.get("data") or []
    if len(datos) >= TECHO_PREVIEW:
        # Truncar en silencio sería peor que fallar: la discrepancia espejo se
        # calcularía sobre un subconjunto arbitrario de socios y nadie lo notaría.
        raise RuntimeError(
            f"respuesta en el techo del preview ({len(datos)} registros) para "
            f"{params}: hay que paginar o usar una subscription key")
    return datos


def _filas(datos: list[dict]) -> list[tuple]:
    """Filas listas para `trade_mirror`, salteando el agregado Mundo."""
    out = []
    for d in datos:
        socio = d.get("partnerCode")
        if socio is None or d.get("reporterCode") is None:
            continue
        out.append((int(d["refYear"]), int(d["reporterCode"]), int(socio),
                    d["flowCode"], d.get("primaryValue"),
                    d.get("fobvalue"), d.get("cifvalue")))
    return out


def ingerir_anio(con: sqlite3.Connection, anio: int) -> tuple[int, int]:
    """Los dos lados de un año. Devuelve (filas lado A, filas lado B)."""
    lado_a = _filas(_pedir(reporterCode=ARGENTINA, period=anio, flowCode="X,M"))
    time.sleep(PAUSA)
    lado_b = _filas(_pedir(partnerCode=ARGENTINA, period=anio, flowCode="X,M"))

    con.executemany(
        "INSERT OR REPLACE INTO trade_mirror "
        "(year, reporter_code, partner_code, flow_code, primary_value, fob_value, cif_value) "
        "VALUES (?,?,?,?,?,?,?)", lado_a + lado_b)
    con.commit()
    return len(lado_a), len(lado_b)


def main(argv: list[str]) -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"no existe {DB_PATH}: correr init_db.py primero")

    desde = int(argv[0]) if argv else DESDE_DEFECTO
    hasta = int(argv[1]) if len(argv) > 1 else time.gmtime().tm_year

    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    total, sin_datos = 0, []
    try:
        for anio in range(desde, hasta + 1):
            try:
                a, b = ingerir_anio(con, anio)
            except RuntimeError as e:
                print(f"  {anio}: ✗ {e}")
                continue
            if a == 0 and b == 0:
                # Normal en el año en curso: Comtrade publica con ~1 año de rezago.
                sin_datos.append(anio)
                print(f"  {anio}: sin datos todavía")
            else:
                total += a + b
                print(f"  {anio}: {a:>4} filas Argentina + {b:>4} filas socios")
            time.sleep(PAUSA)
    finally:
        n = con.execute("SELECT COUNT(*) FROM trade_mirror").fetchone()[0]
        rango = con.execute("SELECT MIN(year), MAX(year) FROM trade_mirror").fetchone()
        con.close()

    print(f"\ntrade_mirror: {n} filas en total, años {rango[0]}..{rango[1]} "
          f"({total} escritas en esta corrida)")
    if sin_datos:
        print(f"sin publicar aún: {', '.join(map(str, sin_datos))}")


if __name__ == "__main__":
    main(sys.argv[1:])
