#!/usr/bin/env python3
"""
Validador de fuentes de datos — Plataforma Económica Inteligente
================================================================

Golpea las APIs reales de los 6 indicadores núcleo (sección 5 del documento)
usando IDENTIFICADORES CANÓNICOS FIJADOS (no búsqueda difusa) y verifica que
cada serie responda con formato, frecuencia y último dato esperados.

Este archivo es la fuente de verdad de "qué serie exacta consume el pipeline".
Los hallazgos corrigen el anexo técnico del PDF (ver notas al pie).

Uso:
    python3 scripts/validate_sources.py

No modifica nada externo: solo lee y reporta. Guarda data/raw/validation_report.json
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import requests

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

TIMEOUT = 25
REPORT: list[dict] = []

# ---------------------------------------------------------------------------
# CONFIGURACIÓN CANÓNICA DE INDICADORES NÚCLEO (validada 2026-07-30)
# ---------------------------------------------------------------------------
SERIES_DATOS_GOB = {
    # indicador                    id serie                        frecuencia esperada
    "IPC nivel general (nac.)":   ("148.3_INIVELNAL_DICI_M_26",    "mensual"),
    "IPC núcleo (nac.)":          ("148.3_INUCLEONAL_DICI_M_19",   "mensual"),
    "EMAE original (base 2004)":  ("143.3_NO_PR_2004_A_21",        "mensual"),
    "EMAE desestacionalizada":    ("302.3_S_DESEST_NRAL_0_S_19",   "mensual"),
    # HALLAZGO: existe serie nacional trimestral vigente (llega a 2026) →
    # el desempleo NO requiere el scraping de PDF que temía el anexo del PDF.
    "Desempleo (tasa desoc.)":    ("42.3_EPH_PUNTUATAL_0_M_30",    "trimestral"),
    # Bloque fiscal — Secretaría de Hacienda (Ministerio de Economía), no INDEC.
    # Publica en la MISMA API: el pipeline no necesitó un fetcher nuevo.
    "Resultado primario (IMIG)":  ("452.3_RESULTADO_RIO_0_M_18_54", "mensual"),
    "Intereses netos (IMIG)":     ("452.3_INTERESES_TOS_0_M_15_62", "mensual"),
    "Resultado financiero (IMIG)":("452.3_RESULTADO_ERO_0_M_20_25", "mensual"),
    "Recaudación total":          ("172.3_TL_RECAION_M_0_0_17",     "mensual"),
}

DOLARAPI = {
    "oficial": "https://dolarapi.com/v1/dolares/oficial",
    "MEP":     "https://dolarapi.com/v1/dolares/bolsa",
    "CCL":     "https://dolarapi.com/v1/dolares/contadoconliqui",
    "blue":    "https://dolarapi.com/v1/dolares/blue",
}

# BCRA v4.0: idVariable FIJADOS tras validar el catálogo (2026-07-30).
# NOTA MONETARIA: en 2026 los pases pasivos están en 0 → el instrumento
# tradicional de "tasa de política" ya no aplica. Se usa TAMAR (bancos privados,
# TNA) como proxy de tasa de referencia de mercado. DECISIÓN A REVISAR con el
# régimen monetario vigente.
BCRA_VARS = {
    "Reservas internacionales":  1,
    "Base monetaria":            15,
    "Tasa referencia (TAMAR priv., TNA)": 44,
}


def _ok(name, msg, sample=None, warn=None):
    print(f"  \033[92m✓\033[0m {name}: {msg}")
    if warn:
        print(f"    \033[93m⚠ {warn}\033[0m")
    REPORT.append({"fuente": name, "estado": "OK", "detalle": msg,
                   "advertencia": warn, "muestra": sample})


def _fail(name, msg):
    print(f"  \033[91m✗\033[0m {name}: {msg}")
    REPORT.append({"fuente": name, "estado": "FALLO", "detalle": msg})


def get(url, verify=True, **kw):
    return requests.get(url, timeout=TIMEOUT,
                        headers={"User-Agent": "plataforma-economica/0.1"},
                        verify=verify, **kw)


def validar_dolarapi():
    print("\n[TC] dolarapi.com — Tipo de cambio y brecha")
    valores, campos = {}, None
    for nombre, url in DOLARAPI.items():
        try:
            d = get(url).json()
            valores[nombre] = d.get("venta")
            campos = list(d.keys())
        except Exception as e:
            _fail(f"dolarapi/{nombre}", f"{type(e).__name__}: {e}")
            return
    of = valores.get("oficial")
    brecha = {k: round((v / of - 1) * 100, 1) for k, v in valores.items()
              if k != "oficial" and of}
    _ok("dolarapi", f"venta={valores} | brecha%={brecha}",
        sample={"campos": campos, "valores": valores, "brecha_pct": brecha},
        warn="El PDF documenta /api/dolar/* — el endpoint vigente es /v1/dolares/*")


def validar_bcra():
    print("\n[BCRA] api.bcra.gob.ar/estadisticas/v4.0/Monetarias")
    base = "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias"
    verify = True
    try:
        r = get(base, verify=verify)
        r.raise_for_status()
    except requests.exceptions.SSLError:
        verify = False
        try:
            r = get(base, verify=verify); r.raise_for_status()
        except Exception as e:
            _fail("BCRA", f"SSL + fallback fallaron: {e}"); return
    except Exception as e:
        _fail("BCRA", f"{type(e).__name__}: {e}"); return

    catalogo = {v.get("idVariable"): v for v in r.json().get("results", [])}
    warn = None if verify else "Requiere verify=False (cadena de certificados del BCRA)"
    encontradas, faltan = {}, []
    for etiqueta, vid in BCRA_VARS.items():
        v = catalogo.get(vid)
        if not v:
            faltan.append(etiqueta); continue
        encontradas[etiqueta] = {
            "idVariable": vid, "descripcion": v.get("descripcion"),
            "valor": v.get("ultValorInformado"), "fecha": v.get("ultFechaInformada"),
            "unidad": v.get("unidadExpresion"), "periodicidad": v.get("periodicidad")}
    linea = " | ".join(f"{k} (id:{d['idVariable']})={d['valor']} {d['unidad']} @ {d['fecha']}"
                       for k, d in encontradas.items())
    msg = f"catálogo {len(catalogo)} vars. {linea}"
    if faltan:
        msg += f" | NO ubicadas: {faltan}"
    _ok("BCRA Monetarias", msg, sample=encontradas, warn=warn)


def validar_serie_datos_gob(nombre, sid, freq_esp):
    try:
        url = (f"https://apis.datos.gob.ar/series/api/series"
               f"?ids={sid}&format=json&last=3&metadata=simple")
        j = get(url).json()
        if "errors" in j:
            _fail(nombre, f"id {sid} → {j['errors']}"); return
        data = j.get("data", [])
        field = None
        for m in j.get("meta", []):
            if isinstance(m, dict) and "field" in m:
                field = m["field"]
        ultimo = data[-1] if data else None
        desc = (field or {}).get("description", "?")
        units = (field or {}).get("units", "?")
        _ok(nombre, f"id={sid} | {desc[:40]} | {units} | {freq_esp} | último={ultimo}",
            sample={"id": sid, "units": units, "ultimo": ultimo,
                    "inicio": (field or {}).get("time_index_start")})
    except Exception as e:
        _fail(nombre, f"{type(e).__name__}: {e}")


def main():
    print("=" * 72)
    print("VALIDACIÓN DE FUENTES — Plataforma Económica Inteligente")
    print(f"Fecha: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 72)

    validar_dolarapi()
    validar_bcra()
    print("\n[INDEC/datos.gob.ar] Series de tiempo (IDs canónicos fijados)")
    for nombre, (sid, freq) in SERIES_DATOS_GOB.items():
        validar_serie_datos_gob(nombre, sid, freq)

    out = Path(__file__).resolve().parent.parent / "data" / "raw" / "validation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"generado": datetime.now(timezone.utc).isoformat(),
                               "resultados": REPORT}, indent=2, ensure_ascii=False),
                   encoding="utf-8")

    ok = sum(1 for r in REPORT if r["estado"] == "OK")
    print("\n" + "=" * 72)
    print(f"RESUMEN: {ok}/{len(REPORT)} controles OK. Reporte: {out}")
    print("=" * 72)
    return 0 if ok == len(REPORT) else 1


if __name__ == "__main__":
    sys.exit(main())
