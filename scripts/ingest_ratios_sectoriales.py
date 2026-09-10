#!/usr/bin/env python3
"""
Ratios sectoriales reales, desde la Cuenta de Generación del Ingreso del INDEC.
================================================================================
Baja, por sector CIIU, las tres series que permiten calcular con qué estructura
opera de verdad cada actividad en Argentina:

    Valor Agregado Bruto pb
    Excedente de explotación bruto        -> margen operativo = EEB / VAB
    Remuneración al trabajo asalariado    -> participación salarial = RTA / VAB

PARA QUÉ. Calibrar el generador de estados contables sintéticos
(`platec/firmas_sinteticas.py`). Sin esto, las distribuciones de un generador son
inventadas y el dataset no dice nada sobre Argentina; con esto, una firma sintética
del sector Comercio tiene la estructura de costos del comercio argentino.

La participación salarial es la que más pesa para el caso de uso: una sociedad
pantalla factura sin nómina. Que eso sea una anomalía y no un número arbitrario
exige saber cuánta nómina tiene una empresa normal de ese sector.

OJO CON LAS SUMAS. Margen operativo y participación salarial NO suman 100%: el VAB
también incluye ingreso mixto e impuestos netos de subsidios. Cuando los subsidios
superan a los impuestos ese componente es negativo y los otros dos pueden pasar del
100% — es lo que se ve en Electricidad, gas y agua, y es correcto, no un error.

Resultado: data/ratios_sectoriales.json, versionado. Es chico y cambia poco.

Uso:
    python3 scripts/ingest_ratios_sectoriales.py
"""
from __future__ import annotations

import collections
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DESTINO = ROOT / "data" / "ratios_sectoriales.json"

BUSCAR = "https://apis.datos.gob.ar/series/api/search"
SERIES = "https://apis.datos.gob.ar/series/api/series"
UA = {"User-Agent": "plataforma-economica/0.1"}
TIMEOUT = 40
PAUSA = 0.6

# Dataset «Cuenta de generación del ingreso» del INDEC.
PREFIJO = "323.1"
COMPONENTES = ("Valor Agregado Bruto pb",
               "Excedente de explotacion bruto",
               "Remuneracion al trabajo asalariado")

# Agregados y sectores que no son empresas, y contaminarían la calibración.
#   - Los TOTAL* son agregados, no actividades.
#   - "Sin distribuir" no es un sector.
#   - Administración pública y Hogares con servicio doméstico no presentan estados
#     contables: su excedente de explotación es cero por construcción, así que
#     entrarían al generador como una firma sin ganancia y sin sentido económico.
EXCLUIR = ("TOTAL", "Sin distribuir",
           "L -Administracion publica y defensa",
           "P -Hogares privados")


def _buscar_series() -> dict[str, str]:
    """Todas las series del dataset, como {id: descripción}."""
    vistos: dict[str, str] = {}
    for termino in COMPONENTES:
        for inicio in (0, 100, 200):
            r = requests.get(BUSCAR, params={"q": termino, "limit": 100, "start": inicio},
                             headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
            for d in r.json().get("data", []):
                f = d["field"]
                if f["id"].startswith(PREFIJO):
                    vistos[f["id"]] = f["description"].strip()
            time.sleep(PAUSA)
    return vistos


def _por_sector(vistos: dict[str, str]) -> dict[str, dict[str, str]]:
    """Agrupa por sector, quedándose con los que tienen los tres componentes."""
    patron = re.compile(r"(.+?)\s+(" + "|".join(map(re.escape, COMPONENTES)) + r")$")
    sec: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for sid, desc in vistos.items():
        m = patron.match(desc)
        if m:
            sec[m.group(1).strip()][m.group(2)] = sid
    return {k: v for k, v in sec.items()
            if len(v) == len(COMPONENTES)
            and not any(k.startswith(x) for x in EXCLUIR)}


def _promedio_reciente(sid: str, n: int = 8) -> tuple[float, str]:
    """
    Promedio de los últimos `n` trimestres y la fecha del último.

    Se promedia y no se toma el último dato: un trimestre suelto puede traer
    estacionalidad o una revisión, y lo que se busca es la ESTRUCTURA del sector,
    no su coyuntura.
    """
    j = requests.get(SERIES, params={"ids": sid, "format": "json", "limit": n,
                                     "sort": "desc"}, headers=UA, timeout=TIMEOUT).json()
    filas = [f for f in j.get("data", []) if f[1] is not None]
    if not filas:
        raise RuntimeError(f"serie sin datos: {sid}")
    return sum(float(f[1]) for f in filas) / len(filas), filas[0][0][:10]


def main() -> None:
    vistos = _buscar_series()
    sectores = _por_sector(vistos)
    print(f"series del dataset {PREFIJO}: {len(vistos)} · "
          f"sectores completos: {len(sectores)}")

    salida, hasta = {}, ""
    for nombre in sorted(sectores):
        ids = sectores[nombre]
        try:
            vab, f = _promedio_reciente(ids["Valor Agregado Bruto pb"])
            eeb, _ = _promedio_reciente(ids["Excedente de explotacion bruto"])
            rta, _ = _promedio_reciente(ids["Remuneracion al trabajo asalariado"])
        except (RuntimeError, KeyError, ValueError) as e:
            print(f"  ✗ {nombre[:44]}: {e}")
            continue
        if vab <= 0:
            print(f"  ✗ {nombre[:44]}: VAB no positivo")
            continue
        hasta = max(hasta, f)
        salida[nombre] = {"margen_operativo": round(eeb / vab, 4),
                          "participacion_salarial": round(rta / vab, 4),
                          "series": ids}
        print(f"  {nombre[:44]:46} margen {eeb / vab:>6.1%}  salarios {rta / vab:>6.1%}")
        time.sleep(PAUSA)

    if len(salida) < 5:
        raise SystemExit(f"solo {len(salida)} sectores: la fuente cambió o falló, no se escribe")

    DESTINO.write_text(json.dumps({
        "fuente": "INDEC · Cuenta de generación del ingreso (datos.gob.ar, dataset 323.1)",
        "nota": ("Margen operativo y participación salarial NO suman 100%: el VAB también "
                 "incluye ingreso mixto e impuestos netos de subsidios, que pueden ser "
                 "negativos."),
        "ultimo_dato": hasta,
        "trimestres_promediados": 8,
        "sectores": salida,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{len(salida)} sectores -> {DESTINO.relative_to(ROOT)} (último dato {hasta})")


if __name__ == "__main__":
    main()
