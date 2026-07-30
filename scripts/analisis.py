#!/usr/bin/env python3
"""
Reporte econométrico de coyuntura — Plataforma Económica Inteligente.
====================================================================
Genera el análisis del relato monetario-cambiario (secc. 10 del documento):
estacionariedad, causalidad de Granger y pass-through cambiario TC -> IPC.
Es el insumo que, en la Etapa 8, la capa de IA narrará en lenguaje natural.

Uso:
    python3 scripts/analisis.py [anio_inicio]   # por defecto 2017
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raíz del proyecto

import warnings

import numpy as np
import pandas as pd

from platec import data, stats
from platec import econometria as ec
from platec import nowcast

warnings.filterwarnings("ignore")


def main(anio_inicio: str = "2017"):
    start = f"{anio_inicio}-01-01"
    df = data.get_frame(["ipc_general", "usd_oficial"], freq="M", how="last", start=start)
    ipc, tc = df["ipc_general"].dropna(), df["usd_oficial"].dropna()

    print("=" * 70)
    print(f"REPORTE ECONOMÉTRICO — muestra desde {anio_inicio} (frecuencia mensual)")
    print("=" * 70)

    print("\n1) COYUNTURA")
    for sid in ["ipc_general", "usd_oficial", "usd_ccl", "tamar_priv", "reservas", "desempleo"]:
        r = stats.resumen(data.get_series(sid))
        print(f"   {data.metadata(sid)['name'][:30]:30} {r['fecha']}  "
              f"últ={r['ultimo']:>12}  Δia={r['var_interanual_%']}%")

    print("\n2) ESTACIONARIEDAD (ADF + KPSS)")
    for nombre, s in [("log(IPC) nivel", np.log(ipc)),
                      ("inflación mensual %", ipc.pct_change() * 100),
                      ("log(TC) nivel", np.log(tc)),
                      ("devaluación mensual %", tc.pct_change() * 100)]:
        print(f"   {nombre:22} -> {ec.test_estacionariedad(s.dropna())}")
    print(f"   Orden integración -> log(IPC): I({ec.orden_integracion(np.log(ipc))}) | "
          f"log(TC): I({ec.orden_integracion(np.log(tc))})")

    print("\n3) CAUSALIDAD DE GRANGER: devaluación -> inflación")
    g = ec.granger(np.log(tc), np.log(ipc), maxlag=6)
    sig = g[g.p_valor < 0.05].index.tolist()
    print(f"   p-valores por rezago: {g['p_valor'].to_dict()}")
    print(f"   Rezagos significativos (p<0.05): {sig or 'ninguno'}")

    print("\n4) PASS-THROUGH CAMBIARIO (rezagos distribuidos, 6 meses)")
    pt = ec.pass_through(tc, ipc, lags=6)
    print(f"   R²={pt.r2}  n={pt.n}")
    print(f"   Acumulado: {pt.acumulado.to_dict()}")
    print(f"   => A 6 meses ~{pt.acumulado.iloc[-1] * 100:.0f}% de una devaluación "
          f"se traslada a precios.")

    print("\n5) VAR + IMPULSO-RESPUESTA (devaluación -> inflación)")
    v = pd.DataFrame({"deval": np.log(tc).diff() * 100,
                      "infl": np.log(ipc).diff() * 100}).dropna()
    var = ec.estimar_var(v, maxlags=8)
    resp = ec.irf(var, shock="deval", respuesta="infl", periodos=12)
    print(f"   {var}")
    print("   Respuesta acumulada de la inflación (pp) a un shock de 1σ en devaluación:")
    print("   ", {f"mes {i}": round(float(resp['acumulada'].iloc[i]), 2) for i in (0, 1, 3, 6, 12)})

    print("\n6) CURVA DE PHILLIPS (trimestral)")
    infl_q = ipc.resample("QS").last().pct_change() * 100
    u_q = data.get_series("desempleo")
    print(f"   {ec.curva_phillips(infl_q, u_q, aumentada=True)}")

    print("\n7) NOWCASTING DE INFLACIÓN (ElasticNet, walk-forward)")
    d = nowcast.construir_features(start=start)
    res = nowcast.evaluar_walk_forward(d, min_train=48)
    print(f"   {res}")
    print(f"   Nowcast mes en curso: {nowcast.nowcast_actual(d):.2f}%  "
          f"(último dato oficial: {d['infl'].iloc[-1]:.2f}%)")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2017")
