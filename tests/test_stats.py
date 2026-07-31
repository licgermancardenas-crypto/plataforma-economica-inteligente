"""Tests de platec.stats — transformaciones puras sobre series."""
import numpy as np
import pandas as pd
import pytest

from platec import stats


@pytest.fixture
def serie_mensual():
    idx = pd.date_range("2020-01-01", periods=24, freq="MS")
    s = pd.Series(np.arange(100, 100 + 24, dtype=float), index=idx, name="x")
    s.attrs["frequency"] = "M"
    return s


def test_variacion_1_periodo(serie_mensual):
    # de 100 a 101 -> +1%
    v = stats.variacion(serie_mensual, 1)
    assert v.iloc[1] == pytest.approx(1.0)
    assert np.isnan(v.iloc[0])  # sin período previo


def test_var_interanual_usa_12_meses(serie_mensual):
    # de 100 (ene-20) a 112 (ene-21) -> +12%
    v = stats.var_interanual(serie_mensual)
    assert v.iloc[12] == pytest.approx(12.0)
    assert np.isnan(v.iloc[11])  # aún no hay 12 meses


def test_var_interanual_toma_frecuencia_de_attrs():
    idx = pd.date_range("2020-01-01", periods=8, freq="QS")
    s = pd.Series(np.arange(100, 108, dtype=float), index=idx)
    s.attrs["frequency"] = "Q"
    v = stats.var_interanual(s)  # sin pasar freq -> lee 'Q' -> 4 períodos
    assert v.iloc[4] == pytest.approx(4.0)


def test_media_movil_min_periods(serie_mensual):
    mm = stats.media_movil(serie_mensual, ventana=3)
    assert np.isnan(mm.iloc[1])          # no completa la ventana
    assert mm.iloc[2] == pytest.approx(101.0)  # (100+101+102)/3


def test_zscore_muestra_completa():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    z = stats.zscore(s)
    assert z.mean() == pytest.approx(0.0, abs=1e-9)
    assert z.iloc[2] == pytest.approx(0.0)  # el valor central es la media


def test_outliers_detecta_pico():
    s = pd.Series([1.0, 1.1, 0.9, 1.0, 50.0, 1.0, 0.95])
    mask = stats.outliers(s, umbral=2.0)
    assert bool(mask.iloc[4]) is True
    assert mask.sum() == 1


def test_deflactar_a_pesos_constantes():
    idx = pd.date_range("2020-01-01", periods=3, freq="MS")
    nominal = pd.Series([100.0, 110.0, 121.0], index=idx)
    ipc = pd.Series([100.0, 110.0, 121.0], index=idx)  # sube igual que el nominal
    real = stats.deflactar(nominal, ipc)
    # deflactado por su propio crecimiento -> real constante en base
    assert real.iloc[0] == pytest.approx(100.0)
    assert real.iloc[1] == pytest.approx(100.0)
    assert real.iloc[2] == pytest.approx(100.0)


def test_brecha_cambiaria():
    idx = pd.date_range("2020-01-01", periods=2, freq="D")
    paralelo = pd.Series([150.0, 200.0], index=idx)
    oficial = pd.Series([100.0, 100.0], index=idx)
    b = stats.brecha(paralelo, oficial)
    assert b.iloc[0] == pytest.approx(50.0)
    assert b.iloc[1] == pytest.approx(100.0)


def test_resumen_estructura(serie_mensual):
    r = stats.resumen(serie_mensual)
    assert r["ultimo"] == pytest.approx(123.0)
    assert r["fecha"] == "2021-12-01"
    assert r["var_periodo_%"] == pytest.approx(round(1 / 122 * 100, 2))
    assert r["var_interanual_%"] is not None


def test_resumen_sin_interanual_si_serie_corta():
    idx = pd.date_range("2020-01-01", periods=5, freq="MS")
    s = pd.Series([1.0, 2, 3, 4, 5], index=idx)
    s.attrs["frequency"] = "M"
    assert stats.resumen(s)["var_interanual_%"] is None
