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


@pytest.fixture
def sistema_causal(idx):
    """x = ruido; z responde a x rezagado. Orden [x, z] => shock en x pega en z."""
    rng = np.random.default_rng(SEED + 8)
    x = rng.standard_normal(len(idx))
    z = np.empty(len(idx))
    z[0] = 0.0
    for t in range(1, len(idx)):
        z[t] = 0.6 * x[t - 1] + 0.3 * z[t - 1] + 0.1 * rng.standard_normal()
    return pd.DataFrame({"x": x, "z": z}, index=idx)


def test_granger_sistema_detecta_la_direccion_correcta(sistema_causal):
    """
    En [x, z] con z respondiendo a x rezagado, x precede a z de forma abrumadora.

    No se exige que z -> x salga NO significativa: con n=300 esa dirección da un
    falso positivo al 5% en ~4 de cada 30 seeds (comprobado), así que afirmarlo
    sería testear la suerte del seed. El contraste que sí es estructural es el
    de magnitudes: la dirección real es órdenes de magnitud más fuerte. El caso
    negativo puro lo cubre `test_granger_sistema_corrige_multiplicidad`.
    """
    r = ec.granger_sistema(sistema_causal, [("x", "z"), ("z", "x")], maxlags=4)
    assert bool(r.loc["x → z", "precede"])
    assert r.loc["x → z", "estadístico F"] > 100 * r.loc["z → x", "estadístico F"]
    assert r.attrs["n"] == len(sistema_causal)
    # el p ajustado nunca puede ser menor que el crudo
    assert (r["p ajustado"] >= r["p_valor"] - 1e-12).all()


def test_granger_sistema_corrige_multiplicidad(idx):
    """Con 6 pares de series independientes, Holm debe apagar los falsos positivos."""
    rng = np.random.default_rng(SEED + 20)
    v = pd.DataFrame({c: rng.standard_normal(len(idx)) for c in "abcd"}, index=idx)
    pares = [("a", "b"), ("b", "a"), ("c", "d"), ("d", "c"), ("a", "c"), ("b", "d")]
    r = ec.granger_sistema(v, pares, maxlags=3)
    assert not r["precede"].any()


def test_granger_robusto_marca_fragil_lo_que_no_aguanta_la_grilla(sistema_causal):
    r = ec.granger_robusto(sistema_causal, [("x", "z"), ("z", "x")],
                           rezagos=(1, 2, 3))
    assert bool(r.loc["x → z", "robusta"])       # causa real: aguanta toda la grilla
    assert not bool(r.loc["z → x", "robusta"])   # dirección falsa: no
    assert r.loc["x → z", "signif. en"] == "3/3"
    assert list(r.columns[:3]) == ["p (rez 1)", "p (rez 2)", "p (rez 3)"]


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


# --- Diagnóstico (pre-testing en tabla) ---
def test_diagnostico_clasifica_orden_de_integracion(idx):
    rng = np.random.default_rng(SEED + 7)
    df = pd.DataFrame({
        "i0": rng.standard_normal(len(idx)),                 # ruido blanco -> I(0)
        "i1": np.cumsum(rng.standard_normal(len(idx))),      # random walk  -> I(1)
    }, index=idx)
    tabla = ec.diagnostico(df)
    assert list(tabla.index) == ["i0", "i1"]
    assert {"ADF p", "KPSS p", "veredicto", "orden I(d)", "n"} <= set(tabla.columns)
    assert tabla.loc["i0", "orden I(d)"] == 0
    assert tabla.loc["i1", "orden I(d)"] == 1


# --- IRF acumulada por bootstrap ---
def test_bootstrap_banda_tiene_ancho_no_nulo(sistema_causal):
    # el motivo de existir de esta función: las bandas MC de statsmodels colapsan
    # sobre el punto en esta versión. Acá el intervalo debe tener ancho real.
    b = ec.irf_acumulada_bootstrap(sistema_causal, "x", "z", periodos=8,
                                   repl=150, seed=1)
    assert len(b.puntual) == len(b.inferior) == len(b.superior) == 9
    assert (b.superior >= b.inferior).all()
    ancho = (b.superior - b.inferior)
    assert (ancho.iloc[1:] > 1e-6).all()          # ninguna banda colapsada
    assert 0 < b.repl <= 150


def test_bootstrap_detecta_respuesta_significativa(sistema_causal):
    b = ec.irf_acumulada_bootstrap(sistema_causal, "x", "z", periodos=8,
                                   repl=200, seed=2)
    # x impulsa z con signo positivo: respuesta acumulada positiva y significativa
    assert b.puntual.iloc[-1] > 0
    assert len(b.significativa_en) > 0


# --- Sensibilidad al orden de Cholesky ---
def test_sensibilidad_orden_una_columna_por_ordenamiento(sistema_causal):
    ordenes = [["x", "z"], ["z", "x"]]
    out = ec.sensibilidad_orden(sistema_causal, "x", "z", ordenes, periodos=6)
    assert list(out.columns) == ["x → z", "z → x"]
    assert len(out) == 7                          # períodos 0..6
    assert out.index.name == "horizonte"


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
