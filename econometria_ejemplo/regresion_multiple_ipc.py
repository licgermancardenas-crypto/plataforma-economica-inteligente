"""
Regresión lineal MÚLTIPLE con datos reales del INDEC (API datos.gob.ar).
Proyecto independiente y autocontenido (no depende de ninguna otra carpeta).

Pregunta: ¿qué explica la inflación mensual (IPC)?
Modelo:
    var_ipc = β0 + β1·var_dolar + β2·var_empleo + β3·var_consumo + ε

Series mensuales usadas:
    IPC Nivel General ............ 148.3_INIVELNAL_DICI_M_26
    Tipo de cambio (peso/dólar) .. 92.2_TIPO_CAMBIION_0_0_21_24  (diario -> promedio mensual)
    Trabajadores registrados ..... 151.1_TL_SIN_TAC_2012_M_15
    Ventas supermercados (reales)  455.1_VENTAS_PRETES_0_M_25_98

OLS estimado a mano con numpy (no requiere statsmodels).
"""
import math
import requests
import numpy as np
import pandas as pd

BASE = "https://apis.datos.gob.ar/series/api/series/"
N = 72  # meses a traer (~6 años)

SERIES = {
    "ipc":     ("148.3_INIVELNAL_DICI_M_26", ""),
    "dolar":   ("92.2_TIPO_CAMBIION_0_0_21_24", "&collapse=month&collapse_aggregation=avg"),
    "empleo":  ("151.1_TL_SIN_TAC_2012_M_15", ""),
    "consumo": ("455.1_VENTAS_PRETES_0_M_25_98", ""),
}


def fetch(series_id, extra=""):
    url = f"{BASE}?ids={series_id}&last={N}&format=json{extra}"
    data = requests.get(url, timeout=30).json()["data"]
    s = pd.DataFrame(data, columns=["fecha", "valor"])
    s["fecha"] = pd.to_datetime(s["fecha"])
    return s.set_index("fecha")["valor"]


def ols(y, X_cols, names):
    """OLS: devuelve coef, std err, t, p-value y R². X_cols = lista de vectores."""
    n = len(y)
    Xmat = np.column_stack([np.ones(n)] + X_cols)   # [1, x1, x2, ...]
    k = Xmat.shape[1]
    beta = np.linalg.lstsq(Xmat, y, rcond=None)[0]
    resid = y - Xmat @ beta
    ss_res = (resid ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot
    r2_adj = 1 - (1 - r2) * (n - 1) / (n - k)
    sigma2 = ss_res / (n - k)
    var_beta = sigma2 * np.linalg.inv(Xmat.T @ Xmat)
    se = np.sqrt(np.diag(var_beta))
    t = beta / se
    p = [2 * (1 - 0.5 * (1 + math.erf(abs(ti) / math.sqrt(2)))) for ti in t]
    return beta, se, t, p, r2, r2_adj, n, k


def reporte(titulo, names, res):
    beta, se, t, p, r2, r2_adj, n, k = res
    print(f"\n=== {titulo}  (n={n}) ===")
    print(f"{'':16}{'coef':>10}{'std err':>10}{'t':>8}{'P>|t|':>9}")
    for nm, b, s, ti, pi in zip(names, beta, se, t, p):
        sig = "*" if pi < 0.05 else " "
        print(f"{nm:16}{b:>10.4f}{s:>10.4f}{ti:>8.2f}{pi:>9.4f} {sig}")
    print(f"R²={r2:.3f}   R² ajustado={r2_adj:.3f}")


# 1) Traer y alinear todas las series en una sola tabla
raw = {k: fetch(*v) for k, v in SERIES.items()}
df = pd.DataFrame(raw).dropna()

# 2) Pasar a variación % mensual (tasas comparables entre series)
for c in df.columns:
    df[c] = df[c].pct_change() * 100
df = df.dropna()

print(f"\nDatos: {len(df)} meses  ({df.index.min():%Y-%m} a {df.index.max():%Y-%m})")
print("\nCorrelación entre explicativas (ojo con multicolinealidad):")
print(df[["dolar", "empleo", "consumo"]].corr().round(2).to_string())

y = df["ipc"].values

# 3a) Modelo SIMPLE: solo el dólar
res1 = ols(y, [df["dolar"].values], ["const", "dolar"])
reporte("Modelo 1 - simple: IPC ~ dolar", ["const", "dolar"], res1)

# 3b) Modelo MÚLTIPLE: las 3 explicativas
res4 = ols(
    y,
    [df["dolar"].values, df["empleo"].values, df["consumo"].values],
    ["const", "dolar", "empleo", "consumo"],
)
reporte("Modelo 2 - múltiple: IPC ~ dolar+empleo+consumo",
        ["const", "dolar", "empleo", "consumo"], res4)

print("\n(*) coeficiente estadísticamente significativo (p < 0,05)")
