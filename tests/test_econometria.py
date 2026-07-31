"""Tests de platec.econometria — con series sintéticas de propiedades conocidas.

La estrategia es generar procesos con estructura controlada (ruido blanco = I(0),
random walk = I(1), un feed causal deval->infl) y verificar que los tests
econométricos los identifican correctamente.
"""
import numpy as np
import pandas as pd
import pytest

from platec import econometria as ec

SEED = 20260731


@pytest.fixture
def idx():
    return pd.date_range("2010-01-01", periods=300, freq="MS")


@pytest.fixture
def ruido_blanco(idx):
    rng = np.random.default_rng(SEED)
    return pd.Series(rng.standard_normal(len(idx)), index=idx)


@pytest.fixture
def random_walk(idx):
    rng = np.random.default_rng(SEED + 1)
    return pd.Series(np.cumsum(rng.standard_normal(len(idx))), index=idx)


# --- Estacionariedad ---
def test_ruido_blanco_es_estacionario(ruido_blanco):
    r = ec.test_estacionariedad(ruido_blanco)
    assert r.veredicto == "estacionaria (I(0))"
    assert r.adf_p < 0.05
    assert r.n == len(ruido_blanco)


def test_random_walk_no_es_estacionario(random_walk):
    r = ec.test_estacionariedad(random_walk)
    assert r.veredicto == "no estacionaria (I(1)+)"
    assert r.adf_p > 0.05


def test_orden_integracion_ruido_blanco_cero(ruido_blanco):
    assert ec.orden_integracion(ruido_blanco) == 0


def test_orden_integracion_random_walk_uno(random_walk):
    assert ec.orden_integracion(random_walk) == 1


# --- Granger ---
def test_granger_detecta_causa_construida(idx):
    rng = np.random.default_rng(SEED + 2)
    x = pd.Series(rng.standard_normal(len(idx)), index=idx)
    # y depende de x rezagado 1 -> x causa-Granger a y
    y = 0.8 * x.shift(1) + 0.1 * rng.standard_normal(len(idx))
    y = pd.Series(y, index=idx)
    res = ec.granger(causa=x, efecto=y, maxlag=3, diferenciar=False)
    assert (res["p_valor"] < 0.05).any()


def test_granger_no_detecta_series_independientes(idx):
    rng = np.random.default_rng(SEED + 3)
    x = pd.Series(rng.standard_normal(len(idx)), index=idx)
    y = pd.Series(rng.standard_normal(len(idx)), index=idx)
    res = ec.granger(causa=x, efecto=y, maxlag=3, diferenciar=False)
    # con series independientes, ningún rezago debería ser fuertemente significativo
    assert (res["p_valor"] < 0.01).sum() == 0


# --- Pass-through ---
def test_pass_through_recupera_estructura(idx):
    rng = np.random.default_rng(SEED + 4)
    # construimos NIVELES tales que sus var. % reproduzcan un pass-through conocido:
    # infl_t = 0.3*deval_t + 0.2*deval_{t-1} + ruido
    deval = pd.Series(rng.normal(2, 1, len(idx)), index=idx)  # % mensual
    infl_pct = 0.3 * deval + 0.2 * deval.shift(1) + rng.normal(0, 0.05, len(idx))
    infl_pct = infl_pct.fillna(0)
    # reconstruir niveles desde las variaciones %
    tc = 100 * (1 + deval / 100).cumprod()
    ipc = 100 * (1 + infl_pct / 100).cumprod()
    pt = ec.pass_through(tc, ipc, lags=3)
    assert pt.coef_por_lag.loc[0] == pytest.approx(0.3, abs=0.05)
    assert pt.coef_por_lag.loc[1] == pytest.approx(0.2, abs=0.05)
    assert pt.acumulado.loc[3] == pytest.approx(0.5, abs=0.08)
    assert pt.r2 > 0.9


# --- VAR + IRF ---
def test_estimar_var_estable_y_irf(idx):
    rng = np.random.default_rng(SEED + 5)
    a = pd.Series(rng.standard_normal(len(idx)), index=idx)
    b = 0.5 * a.shift(1).fillna(0) + rng.standard_normal(len(idx))
    df = pd.DataFrame({"a": a, "b": pd.Series(b, index=idx)})
    var = ec.estimar_var(df, maxlags=4)
    assert var.estable is True
    assert var.orden >= 1
    irf = ec.irf(var, shock="a", respuesta="b", periodos=6)
    assert len(irf) == 7           # períodos 0..6
    assert {"irf", "acumulada"} <= set(irf.columns)
    # respuesta acumulada monótona en la relación construida (a impulsa b)
    assert irf["acumulada"].iloc[-1] > irf["acumulada"].iloc[0]


# --- Curva de Phillips ---
def test_curva_phillips_estructura():
    idxq = pd.date_range("2005-01-01", periods=60, freq="QS")
    rng = np.random.default_rng(SEED + 6)
    u = pd.Series(rng.uniform(5, 12, 60), index=idxq)
    # pendiente negativa construida: más desempleo -> menos inflación
    pi = 20 - 1.5 * u + rng.normal(0, 0.5, 60)
    pi = pd.Series(pi, index=idxq)
    ph = ec.curva_phillips(pi, u, aumentada=False)
    assert ph.beta_desempleo < 0
    assert ph.p_valor < 0.05
    assert ph.forma == "nivel"
