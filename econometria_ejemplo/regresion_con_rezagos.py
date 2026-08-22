"""
Prueba real con datos del INDEC: ¿mejora el modelo si agregamos REZAGOS?

Idea econométrica: los efectos en macro no son instantáneos.
  - El dólar de ESTE mes y el del mes PASADO pueden empujar precios (pass-through con rezago).
  - La inflación tiene INERCIA: el IPC de este mes depende del de los meses anteriores.

Comparamos 3 modelos sobre la MISMA muestra:
  M1: IPC ~ dolar                                  (contemporáneo simple)
  M2: IPC ~ dolar + dolar(-1) + consumo(-1)        (con rezagos de X)
  M3: M2 + ipc(-1)                                 (agrega inercia inflacionaria)

Series mensuales (API datos.gob.ar / INDEC):
  IPC .......... 148.3_INIVELNAL_DICI_M_26
  Dólar ........ 92.2_TIPO_CAMBIION_0_0_21_24  (diario -> promedio mensual)
  Consumo ...... 455.1_VENTAS_PRETES_0_M_25_98 (ventas supermercados reales)
"""
import math
import requests
import numpy as np
import pandas as pd

BASE = "https://apis.datos.gob.ar/series/api/series/"
N = 84  # ~7 años

SERIES = {
    "ipc":     ("148.3_INIVELNAL_DICI_M_26", ""),
    "dolar":   ("92.2_TIPO_CAMBIION_0_0_21_24", "&collapse=month&collapse_aggregation=avg"),
    "consumo": ("455.1_VENTAS_PRETES_0_M_25_98", ""),
}


def fetch(series_id, extra=""):
    url = f"{BASE}?ids={series_id}&last={N}&format=json{extra}"
    data = requests.get(url, timeout=30).json()["data"]
    s = pd.DataFrame(data, columns=["fecha", "valor"])
    s["fecha"] = pd.to_datetime(s["fecha"])
    return s.set_index("fecha")["valor"]


def ols(df, y_col, x_cols):
    y = df[y_col].values
    n = len(y)
    Xmat = np.column_stack([np.ones(n)] + [df[c].values for c in x_cols])
    k = Xmat.shape[1]
    beta = np.linalg.lstsq(Xmat, y, rcond=None)[0]
    resid = y - Xmat @ beta
    ss_res = (resid ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot
    r2_adj = 1 - (1 - r2) * (n - 1) / (n - k)
    sigma2 = ss_res / (n - k)
    se = np.sqrt(np.diag(sigma2 * np.linalg.inv(Xmat.T @ Xmat)))
    t = beta / se
    p = [2 * (1 - 0.5 * (1 + math.erf(abs(ti) / math.sqrt(2)))) for ti in t]
    return dict(names=["const"] + x_cols, beta=beta, se=se, t=t, p=p,
                r2=r2, r2_adj=r2_adj, n=n)


def reporte(titulo, r):
    print(f"\n=== {titulo}  (n={r['n']}) ===")
    print(f"{'':16}{'coef':>10}{'std err':>10}{'t':>8}{'P>|t|':>9}")
    for nm, b, s, ti, pi in zip(r["names"], r["beta"], r["se"], r["t"], r["p"]):
        sig = "*" if pi < 0.05 else " "
        print(f"{nm:16}{b:>10.4f}{s:>10.4f}{ti:>8.2f}{pi:>9.4f} {sig}")
    print(f"R²={r['r2']:.3f}   R² ajustado={r['r2_adj']:.3f}")


# 1) Traer, alinear y pasar a variación % mensual
raw = {k: fetch(*v) for k, v in SERIES.items()}
df = pd.DataFrame(raw).dropna()
for c in df.columns:
    df[c] = df[c].pct_change() * 100
df = df.dropna()

# 2) Construir rezagos (t-1)
df["dolar_lag1"]   = df["dolar"].shift(1)
df["consumo_lag1"] = df["consumo"].shift(1)
df["ipc_lag1"]     = df["ipc"].shift(1)
df = df.dropna()   # todos los modelos usan la MISMA muestra (comparables)

print(f"\nDatos: {len(df)} meses  ({df.index.min():%Y-%m} a {df.index.max():%Y-%m})")

reporte("M1  IPC ~ dolar",
        ols(df, "ipc", ["dolar"]))
reporte("M2  IPC ~ dolar + dolar(-1) + consumo(-1)",
        ols(df, "ipc", ["dolar", "dolar_lag1", "consumo_lag1"]))
reporte("M3  + inercia: IPC ~ dolar + dolar(-1) + consumo(-1) + ipc(-1)",
        ols(df, "ipc", ["dolar", "dolar_lag1", "consumo_lag1", "ipc_lag1"]))

print("\n(*) significativo (p<0,05).  Compará el R² ajustado entre modelos.")
