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


def granger_sistema(v: pd.DataFrame, pares: list[tuple[str, str]],
                    maxlags: int = 6, metodo: str = "holm") -> pd.DataFrame:
    """
    Granger de sistema: un test de Wald CONJUNTO por par sobre el VAR(p) ajustado,
    con p elegido por AIC, más corrección por multiplicidad.

    Por qué no alcanza `granger()` para armar tablas: esa función devuelve un
    p-valor por rezago y el uso natural es quedarse con el mínimo. Eso es
    selección post-hoc — con 10 rezagos el mínimo de 10 estadísticos correlacionados
    cae bajo 0,05 mucho más del 5% de las veces bajo H0. En una tabla de N pares el
    problema se multiplica. Acá se hace UN test por par (H0: todos los rezagos de
    `causa` son cero en la ecuación de `efecto`) y se ajustan los N p-valores.

    Comprobado en este proyecto: con minimización sobre 10 rezagos, riesgo país →
    TC daba p=0,0005 en el régimen sin cepo; el Wald conjunto sobre el mismo VAR da
    p=0,047, que no sobrevive la corrección. La conclusión se daba vuelta.

    `metodo` es cualquiera de statsmodels.stats.multitest ('holm', 'bonferroni',
    'fdr_bh'). Holm por defecto: controla el error de familia sin ser tan
    conservador como Bonferroni.
    """
    from statsmodels.stats.multitest import multipletests

    d = v.dropna()
    base = VAR(d).fit(maxlags=maxlags, ic="aic")
    # Un VAR(0) no tiene rezagos que testear y `test_causality` lanza RuntimeError.
    # Pasa cuando las series son casi independientes (el AIC elige 0, correctamente).
    # Se fuerza el mínimo de 1: el test entonces devuelve el p que corresponde —
    # típicamente no significativo, que es la respuesta correcta.
    p_ar = max(base.k_ar, 1)
    res = base if base.k_ar == p_ar else VAR(d).fit(p_ar)
    filas = []
    for causa, efecto in pares:
        w = res.test_causality(efecto, [causa], kind="f")
        filas.append({"relación": f"{causa} → {efecto}", "p_valor": float(w.pvalue),
                      "estadístico F": round(float(w.test_statistic), 2)})
    out = pd.DataFrame(filas)
    out["p ajustado"] = multipletests(out["p_valor"], method=metodo)[1]
    out["precede"] = out["p ajustado"] < 0.05
    out["p_valor"] = out["p_valor"].round(4)
    out["p ajustado"] = out["p ajustado"].round(4)
    out.attrs["rezagos"] = p_ar
    out.attrs["n"] = len(d)
    out.attrs["metodo"] = metodo
    return out.set_index("relación")


def granger_robusto(v: pd.DataFrame, pares: list[tuple[str, str]],
                    rezagos: tuple[int, ...] = (1, 2, 3, 5, 10, 15),
                    metodo: str = "holm") -> pd.DataFrame:
    """
    `granger_sistema` repetido a rezago FIJO sobre una grilla, para ver si la
    conclusión depende de la selección del orden del VAR.

    Motivo: en datos diarios el AIC no converge —en este proyecto eligió 3, 15 y 14
    según dónde se pusiera el tope, mientras BIC elegía 0 y HQIC 1—. Con esa
    dispersión, "el p-valor al orden que eligió el AIC" es un número arbitrario.
    Una relación que sólo aparece a un rezago puntual y desaparece en los vecinos
    es ruido; una que aguanta toda la grilla es señal.

    Devuelve una columna de p ajustados por rezago (Holm dentro de cada rezago, que
    es la familia de hipótesis comparables) y una columna `robusta` = significativa
    en TODOS los rezagos probados. Esa última es la que hay que leer.
    """
    from statsmodels.stats.multitest import multipletests

    d = v.dropna()
    cols = {}
    for p_fijo in rezagos:
        res = VAR(d).fit(p_fijo)
        ps = [float(res.test_causality(ef, [ca], kind="f").pvalue) for ca, ef in pares]
        cols[f"p (rez {p_fijo})"] = multipletests(ps, method=metodo)[1]
    out = pd.DataFrame(cols, index=[f"{c} → {e}" for c, e in pares]).round(4)
    out["robusta"] = (out < 0.05).all(axis=1)
    out["signif. en"] = (out.drop(columns="robusta") < 0.05).sum(axis=1).astype(str) \
                        + f"/{len(rezagos)}"
    out.index.name = "relación"
    out.attrs["rezagos"] = list(rezagos)
    out.attrs["n"] = len(d)
    return out


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


# ---------------------------------------------------------------------------
# 8. Incertidumbre de la impulso-respuesta (bootstrap propio)
# ---------------------------------------------------------------------------
# Por qué no se usan las bandas de statsmodels: `VARResults.irf_resim` (motor de
# `errband_mc`/`cum_errband_mc`) devuelve en esta versión (0.14.6 + numpy 2.x)
# las N réplicas IDÉNTICAS entre sí —desvío entre réplicas ~1e-15—, así que las
# bandas colapsan sobre el estimador puntual. Un intervalo de ancho cero no es un
# error visible: es un gráfico que miente con cara de rigor. Se implementa acá el
# bootstrap de residuos estándar (Runkle 1987; Lütkepohl 2005, cap. 3.7).
@dataclass
class IRFBandas:
    puntual: pd.Series        # respuesta acumulada por horizonte (pp)
    inferior: pd.Series
    superior: pd.Series
    orden: list               # orden de Cholesky usado (más exógena primero)
    p: int                    # rezagos del VAR
    repl: int
    signif: float
    n: int

    @property
    def significativa_en(self) -> list:
        """Horizontes donde el intervalo no contiene al cero."""
        return [h for h in self.puntual.index
                if not (self.inferior[h] <= 0 <= self.superior[h])]

    def __str__(self):
        h = self.puntual.index[-1]
        return (f"IRF acumulada h={h}: {self.puntual[h]:.2f} pp "
                f"[{self.inferior[h]:.2f}, {self.superior[h]:.2f}] "
                f"({int((1-self.signif)*100)}%, {self.repl} réplicas)")


def _irf_acum_ortogonal(datos: np.ndarray, p: int, i: int, j: int,
                        periodos: int) -> np.ndarray:
    """IRF ortogonalizada acumulada de j ante shock en i, estimando un VAR(p) por OLS."""
    res = VAR(datos).fit(p)
    an = res.irf(periodos)
    return an.orth_cum_effects[:, j, i]


def irf_acumulada_bootstrap(v: pd.DataFrame, shock: str, respuesta: str,
                            periodos: int = 12, repl: int = 600,
                            signif: float = 0.05, seed: int = 7,
                            maxlags: int = 6) -> IRFBandas:
    """
    Respuesta acumulada de `respuesta` ante un shock de 1 d.e. en `shock`, con
    intervalo por bootstrap de residuos.

    Procedimiento: se estima el VAR(p) (p por AIC) sobre la muestra real; en cada
    réplica se remuestrean con reemplazo los residuos, se resimula el sistema
    partiendo de las primeras p observaciones reales, se REESTIMA el VAR con el
    mismo p y se recalcula la IRF. El intervalo son los percentiles signif/2 y
    1-signif/2 de las réplicas.

    El orden de las columnas de `v` define la identificación de Cholesky: la
    primera variable es la más exógena contemporáneamente. Esa elección no es
    inocua — ver `sensibilidad_orden`.

    Advertencia metodológica: es un intervalo percentil simple, sin la corrección
    de sesgo de Kilian (1998). En muestras cortas y con raíces cercanas a la
    unidad tiende a subcubrir; leerlo como orden de magnitud de la incertidumbre,
    no como un intervalo exacto.
    """
    d = v.dropna()
    nombres = list(d.columns)
    i, j = nombres.index(shock), nombres.index(respuesta)
    datos = d.to_numpy()

    base = VAR(datos).fit(maxlags=maxlags, ic="aic")
    p = max(base.k_ar, 1)
    puntual = _irf_acum_ortogonal(datos, p, i, j, periodos)

    intercepto = base.params[0]
    coefs = base.coefs                      # (p, k, k)
    resid = base.resid                      # (T-p, k)
    T, k = datos.shape
    rng = np.random.default_rng(seed)

    simuladas = np.empty((repl, periodos + 1))
    fallidas = 0
    for b in range(repl):
        u = resid[rng.integers(0, len(resid), size=len(resid))]
        sim = np.empty((T, k))
        sim[:p] = datos[:p]                 # arranque con las p reales
        for t in range(p, T):
            x = intercepto.copy()
            for l in range(p):
                x = x + coefs[l] @ sim[t - 1 - l]
            sim[t] = x + u[t - p]
        try:
            simuladas[b] = _irf_acum_ortogonal(sim, p, i, j, periodos)
        except (np.linalg.LinAlgError, ValueError):
            simuladas[b] = np.nan           # réplica explosiva: se descarta
            fallidas += 1

    validas = simuladas[~np.isnan(simuladas).any(axis=1)]
    lo = np.percentile(validas, 100 * signif / 2, axis=0)
    hi = np.percentile(validas, 100 * (1 - signif / 2), axis=0)
    idx = pd.RangeIndex(periodos + 1, name="horizonte")
    return IRFBandas(
        puntual=pd.Series(puntual, index=idx), inferior=pd.Series(lo, index=idx),
        superior=pd.Series(hi, index=idx), orden=nombres, p=p,
        repl=len(validas), signif=signif, n=len(d))


def sensibilidad_orden(v: pd.DataFrame, shock: str, respuesta: str,
                       ordenes: list, periodos: int = 12,
                       maxlags: int = 6) -> pd.DataFrame:
    """
    La misma IRF acumulada bajo distintos ordenamientos de Cholesky.

    La descomposición de Cholesky impone una cadena causal contemporánea que los
    datos NO identifican: es un supuesto del analista. Si la respuesta cambia
    mucho al reordenar, la conclusión depende del supuesto y no de la evidencia.
    Devuelve un DataFrame con una columna por ordenamiento (etiquetada con el
    orden usado) indexado por horizonte.
    """
    out = {}
    for orden in ordenes:
        d = v[list(orden)].dropna()
        i, j = list(orden).index(shock), list(orden).index(respuesta)
        base = VAR(d.to_numpy()).fit(maxlags=maxlags, ic="aic")
        out[" → ".join(orden)] = _irf_acum_ortogonal(
            d.to_numpy(), max(base.k_ar, 1), i, j, periodos)
    return pd.DataFrame(out, index=pd.RangeIndex(periodos + 1, name="horizonte"))


def diagnostico(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tabla de pre-testing por serie: ADF, KPSS, veredicto y orden de integración.
    Es lo que justifica (o no) estimar el VAR en diferencias; hasta ahora vivía
    solo en el reporte de consola.
    """
    filas = []
    for col in df.columns:
        r = test_estacionariedad(df[col].dropna())
        filas.append({"serie": col, "ADF p": round(r.adf_p, 3),
                      "KPSS p": round(r.kpss_p, 3), "veredicto": r.veredicto,
                      "orden I(d)": orden_integracion(df[col]), "n": r.n})
    return pd.DataFrame(filas).set_index("serie")
