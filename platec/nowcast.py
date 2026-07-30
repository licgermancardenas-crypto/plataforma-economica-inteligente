"""
platec.nowcast — nowcasting de inflación mensual con ML (Etapa 7).
==================================================================
Estima el IPC del mes en curso ANTES de la publicación oficial del INDEC, usando
variables de alta frecuencia ya disponibles (tipo de cambio diario, brecha, tasa)
más la inercia inflacionaria.

Enfoque:
  - Features mensuales construidos desde series diarias/mensuales:
      * devaluación del mes (oficial y CCL, fin de mes)
      * brecha promedio del mes
      * inflación rezagada (inercia)
  - Modelo: regresión regularizada (ElasticNet) — pocas observaciones, muchas
    correlaciones; la regularización evita sobreajuste.
  - Validación: walk-forward (expanding window) fuera de muestra, comparado contra
    un benchmark ingenuo (random walk: la inflación del mes será la del mes pasado).

Métrica: RMSE fuera de muestra. Si el modelo no le gana al random walk, no sirve.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNetCV
from sklearn.metrics import mean_squared_error

from . import data


def construir_features(start: str = "2017-01-01") -> pd.DataFrame:
    """DataFrame mensual con el target (inflación) y los predictores de alta frecuencia."""
    # NOTA: TAMAR se excluye a propósito — solo existe desde oct-2024 y truncaría
    # la muestra de entrenamiento. Se usan features con cobertura desde 2017.
    ipc = data.get_series("ipc_general")
    of = data.get_series("usd_oficial")
    ccl = data.get_series("usd_ccl")

    m_ipc = ipc.resample("MS").last()
    m_of = of.resample("MS").last()
    m_ccl = ccl.resample("MS").last()
    m_brecha = ((ccl / of.reindex(ccl.index).ffill() - 1) * 100).resample("MS").mean()

    infl = m_ipc.pct_change() * 100
    df = pd.DataFrame({
        "infl": infl,
        "deval_of": m_of.pct_change() * 100,
        "deval_ccl": m_ccl.pct_change() * 100,
        "brecha": m_brecha,
    })
    # Inercia: inflación de meses previos (disponible al nowcastear el mes t)
    df["infl_l1"] = df["infl"].shift(1)
    df["infl_l2"] = df["infl"].shift(2)
    return df.loc[start:].dropna()


@dataclass
class ResultadoNowcast:
    rmse_modelo: float
    rmse_naive: float
    mejora_pct: float          # % de reducción de error vs. naive
    n_test: int
    coef: dict                 # importancia de cada feature (última estimación)

    def __str__(self):
        v = "GANA" if self.mejora_pct > 0 else "no supera"
        return (f"Nowcast RMSE={self.rmse_modelo:.2f} vs naive={self.rmse_naive:.2f} "
                f"({v} al benchmark, {self.mejora_pct:+.0f}%) sobre {self.n_test} meses")


FEATURES = ["deval_of", "deval_ccl", "brecha", "infl_l1", "infl_l2"]


def evaluar_walk_forward(df: pd.DataFrame, min_train: int = 36) -> ResultadoNowcast:
    """
    Validación fuera de muestra con ventana expansiva: para cada mes t del período
    de test, se entrena solo con datos < t y se predice t. Compara contra el
    benchmark ingenuo (inflación_t ≈ inflación_{t-1}).
    """
    y = df["infl"].values
    X = df[FEATURES].values
    preds, reales, naive = [], [], []
    modelo = None
    for t in range(min_train, len(df)):
        modelo = ElasticNetCV(cv=5, max_iter=10000, l1_ratio=[.2, .5, .8])
        modelo.fit(X[:t], y[:t])
        preds.append(modelo.predict(X[t:t + 1])[0])
        reales.append(y[t])
        naive.append(df["infl_l1"].values[t])  # random walk
    rmse_m = float(np.sqrt(mean_squared_error(reales, preds)))
    rmse_n = float(np.sqrt(mean_squared_error(reales, naive)))
    coef = dict(zip(FEATURES, np.round(modelo.coef_, 3))) if modelo is not None else {}
    return ResultadoNowcast(
        rmse_modelo=round(rmse_m, 3), rmse_naive=round(rmse_n, 3),
        mejora_pct=round((1 - rmse_m / rmse_n) * 100, 1),
        n_test=len(reales), coef=coef)


def nowcast_actual(df: pd.DataFrame) -> float:
    """Estima la inflación del último mes disponible entrenando con todo el histórico previo."""
    modelo = ElasticNetCV(cv=5, max_iter=10000, l1_ratio=[.2, .5, .8])
    modelo.fit(df[FEATURES].values[:-1], df["infl"].values[:-1])
    return float(modelo.predict(df[FEATURES].values[-1:])[0])
