"""
platec.econometria — capa de modelado econométrico (sección 10 del documento).
==============================================================================
Convierte las series en relaciones: estacionariedad, orden de integración,
causalidad de Granger, cointegración y pass-through cambiario. Se apoya en
statsmodels.

Regla metodológica que atraviesa el módulo: NADA de VAR/regresión en niveles sin
antes verificar estacionariedad. Casi todas estas series macro son I(1); trabajar
en niveles sin cointegración produce regresiones espurias.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tools.sm_exceptions import InterpolationWarning
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller, kpss, grangercausalitytests
from statsmodels.tsa.vector_ar.vecm import coint_johansen


# ---------------------------------------------------------------------------
# 1. Estacionariedad y orden de integración
# ---------------------------------------------------------------------------
@dataclass
class ResultadoEstacionariedad:
    adf_p: float
    kpss_p: float
    veredicto: str          # 'estacionaria (I(0))', 'no estacionaria (I(1)+)', 'ambiguo'
    n: int

    def __str__(self):
        return (f"ADF p={self.adf_p:.3f} | KPSS p={self.kpss_p:.3f} "
                f"| {self.veredicto} (n={self.n})")


def test_estacionariedad(s: pd.Series, regresion: str = "c") -> ResultadoEstacionariedad:
    """
    Combina ADF (H0: raíz unitaria) y KPSS (H0: estacionariedad). El cruce de ambos
    da un veredicto robusto:
      - ADF rechaza y KPSS no rechaza  -> estacionaria I(0)
      - ADF no rechaza y KPSS rechaza  -> no estacionaria I(1)+
      - en desacuerdo                  -> ambiguo (inspeccionar)
    """
    s = s.dropna()
    adf_p = adfuller(s, regression=regresion, autolag="AIC")[1]
    # KPSS usa 'c' o 'ct'; mapear. El InterpolationWarning aparece cuando el
    # estadístico cae fuera de la tabla (p-valor extremo): es informativo, no un error.
    kpss_reg = "c" if regresion == "c" else "ct"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InterpolationWarning)
        kpss_p = kpss(s, regression=kpss_reg, nlags="auto")[1]
    adf_estac = adf_p < 0.05      # rechaza raíz unitaria
    kpss_estac = kpss_p >= 0.05   # no rechaza estacionariedad
    if adf_estac and kpss_estac:
        v = "estacionaria (I(0))"
    elif not adf_estac and not kpss_estac:
        v = "no estacionaria (I(1)+)"
    else:
        v = "ambiguo"
    return ResultadoEstacionariedad(adf_p, kpss_p, v, len(s))


def orden_integracion(s: pd.Series, max_d: int = 2) -> int:
    """Nº de diferencias necesarias para volver la serie estacionaria (0, 1 o 2)."""
    x = s.dropna()
    for d in range(max_d + 1):
        if test_estacionariedad(x).veredicto == "estacionaria (I(0))":
            return d
        x = x.diff().dropna()
    return max_d


# ---------------------------------------------------------------------------
# 2. Causalidad de Granger
# ---------------------------------------------------------------------------
def granger(causa: pd.Series, efecto: pd.Series, maxlag: int = 6,
            diferenciar: bool = True) -> pd.DataFrame:
    """
    ¿`causa` ayuda a predecir `efecto`? Devuelve p-valores por rezago.
    Por defecto trabaja en diferencias (las series suelen ser I(1)).
    p < 0.05 en un rezago sugiere causalidad de Granger de `causa` -> `efecto`.
    """
    df = pd.concat([efecto, causa], axis=1).dropna()
    if diferenciar:
        df = df.diff().dropna()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        res = grangercausalitytests(df, maxlag=maxlag, verbose=False)
    filas = [{"lag": k, "p_valor": round(v[0]["ssr_ftest"][1], 4)} for k, v in res.items()]
    return pd.DataFrame(filas).set_index("lag")


# ---------------------------------------------------------------------------
# 3. Cointegración (Johansen)
# ---------------------------------------------------------------------------
def cointegracion_johansen(df: pd.DataFrame, det_order: int = 0, k_ar_diff: int = 2) -> dict:
    """
    Test de Johansen sobre un DataFrame de series (en niveles). Devuelve el rango
    de cointegración: nº de relaciones de equilibrio de largo plazo.
    rango >= 1 habilita modelar con VECM en lugar de VAR en diferencias.
    """
    d = df.dropna()
    jo = coint_johansen(d, det_order, k_ar_diff)
    traza = jo.lr1                    # estadístico de la traza
    crit = jo.cvt[:, 1]              # valores críticos al 5%
    rango = int(np.sum(traza > crit))
    return {
        "rango_cointegracion": rango,
        "traza": np.round(traza, 2).tolist(),
        "critico_5pct": np.round(crit, 2).tolist(),
        "interpretacion": (f"{rango} relación(es) de cointegración -> usar VECM"
                           if rango else "sin cointegración -> VAR en diferencias"),
    }


# ---------------------------------------------------------------------------
# 4. Pass-through cambiario (TC -> IPC)
# ---------------------------------------------------------------------------
@dataclass
class PassThrough:
    coef_por_lag: pd.Series      # elasticidad de la inflación a la devaluación por rezago
    acumulado: pd.Series         # pass-through acumulado hasta cada rezago
    r2: float
    n: int


@dataclass
class ResultadoVAR:
    orden: int
    variables: list
    res: object          # VARResults de statsmodels
    estable: bool        # todas las raíces dentro del círculo unitario

    def __str__(self):
        est = "estable" if self.estable else "INESTABLE"
        return f"VAR({self.orden}) sobre {self.variables} — {est}"


def estimar_var(df: pd.DataFrame, maxlags: int = 8, ic: str = "aic") -> ResultadoVAR:
    """
    Ajusta un VAR sobre series ESTACIONARIAS (usar variaciones, no niveles).
    Selecciona el nº de rezagos por criterio de información (`ic`).
    Verifica estabilidad (raíces del polinomio dentro del círculo unitario).
    """
    d = df.dropna()
    res = VAR(d).fit(maxlags=maxlags, ic=ic)
    return ResultadoVAR(orden=res.k_ar, variables=list(d.columns), res=res,
                        estable=bool(res.is_stable(verbose=False)))


def irf(var: ResultadoVAR, shock: str, respuesta: str, periodos: int = 12) -> pd.DataFrame:
    """
    Función impulso-respuesta ortogonalizada (Cholesky): respuesta de `respuesta`
    ante un shock de 1 desvío estándar en `shock`. Devuelve la respuesta período a
    período y la acumulada. OJO: el orden de las columnas del df define la
    identificación de Cholesky (variable más exógena primero).
    """
    an = var.res.irf(periodos)
    names = var.res.names
    i, j = names.index(shock), names.index(respuesta)
    return pd.DataFrame({
        "irf": an.orth_irfs[:, j, i],
        "acumulada": an.orth_cum_effects[:, j, i],
    }, index=range(periodos + 1))


# ---------------------------------------------------------------------------
# 6. Curva de Phillips (desempleo <-> inflación)
# ---------------------------------------------------------------------------
@dataclass
class Phillips:
    beta_desempleo: float     # pendiente: efecto del desempleo sobre la inflación
    p_valor: float
    r2: float
    n: int
    forma: str

    def __str__(self):
        signif = "significativa" if self.p_valor < 0.05 else "NO significativa"
        return (f"Phillips ({self.forma}): β_u={self.beta_desempleo:+.3f} "
                f"(p={self.p_valor:.3f}, {signif}) | R²={self.r2:.3f} n={self.n}")


def curva_phillips(inflacion: pd.Series, desempleo: pd.Series,
                   aumentada: bool = True) -> Phillips:
    """
    Curva de Phillips en frecuencia trimestral. Forma aumentada por expectativas
    (backward): π_t = α + β·u_t + γ·π_{t-1} + ε. Se espera β < 0 (más desempleo,
    menos inflación). En economías con inflación de costos/monetaria la relación
    suele ser débil o plana — el resultado hay que leerlo con ese contexto.
    """
    df = pd.concat({"pi": inflacion, "u": desempleo}, axis=1).dropna()
    X = df[["u"]].copy()
    forma = "nivel"
    if aumentada:
        X["pi_lag"] = df["pi"].shift(1)
        forma = "aumentada por expectativas"
    d = pd.concat([df["pi"], X], axis=1).dropna()
    m = sm.OLS(d["pi"], sm.add_constant(d.iloc[:, 1:])).fit()
    return Phillips(beta_desempleo=round(float(m.params["u"]), 4),
                    p_valor=round(float(m.pvalues["u"]), 4),
                    r2=round(float(m.rsquared), 3), n=int(m.nobs), forma=forma)


def pass_through(tc: pd.Series, ipc: pd.Series, lags: int = 6) -> PassThrough:
    """
    Estima el traslado de una devaluación a precios con un modelo de rezagos
    distribuidos sobre tasas de variación mensuales:

        π_t = α + Σ_{i=0..L} β_i · devaluación_{t-i} + ε_t

    donde π es la inflación mensual (%) y devaluación es la var. mensual del TC (%).
    El pass-through ACUMULADO tras L meses es Σ β_i (cuánto de la devaluación se
    trasladó a precios). Trabaja en variaciones (series estacionarias).
    """
    infl = ipc.pct_change() * 100
    deval = tc.pct_change() * 100
    df = pd.concat({"infl": infl, "deval": deval}, axis=1).dropna()
    X = pd.concat({f"deval_l{i}": df["deval"].shift(i) for i in range(lags + 1)}, axis=1)
    d = pd.concat([df["infl"], X], axis=1).dropna()
    modelo = sm.OLS(d["infl"], sm.add_constant(d.iloc[:, 1:])).fit()
    betas = modelo.params.drop("const")
    betas.index = range(lags + 1)
    return PassThrough(coef_por_lag=betas.round(3),
                       acumulado=betas.cumsum().round(3),
                       r2=round(modelo.rsquared, 3), n=int(modelo.nobs))
