"""Tests de platec.insights — lectura automática de series (funciones puras)."""
import numpy as np
import pandas as pd
import pytest

from platec import insights as ins


@pytest.fixture
def idx():
    return pd.date_range("2018-01-01", periods=60, freq="MS")


def _serie(valores, idx, freq="M"):
    s = pd.Series(valores, index=idx[: len(valores)], dtype=float)
    s.attrs["frequency"] = freq
    return s


def test_posicion_historica_maximo(idx):
    s = _serie(np.arange(1, 61, dtype=float), idx)  # monótona creciente
    assert ins.posicion_historica(s) == pytest.approx(100.0)


def test_posicion_historica_minimo(idx):
    s = _serie(np.arange(60, 0, -1, dtype=float), idx)  # monótona decreciente
    assert ins.posicion_historica(s) == pytest.approx(100 / 60)  # último = mínimo


def test_racha_alza(idx):
    s = _serie([1, 2, 3, 4, 5, 6], idx)
    assert ins.racha(s) == 5  # 5 subas consecutivas


def test_racha_baja(idx):
    s = _serie([6, 5, 4, 3], idx)
    assert ins.racha(s) == -3


def test_racha_se_corta(idx):
    s = _serie([1, 2, 3, 2.9], idx)  # última es baja tras 2 subas
    assert ins.racha(s) == -1


def test_momentum_positivo_si_acelera(idx):
    # nivel bajo estable y luego un salto reciente -> MM corta > MM larga
    s = _serie([10] * 11 + [20, 20, 20], idx)
    assert ins.momentum(s, corta=3, larga=12) > 0


def test_momentum_nan_si_muestra_corta(idx):
    s = _serie([1, 2, 3], idx)
    assert np.isnan(ins.momentum(s, corta=3, larga=12))


def test_es_anomalia_detecta_pico(idx):
    base = [10.0 + 0.1 * (i % 3) for i in range(40)]
    base[-1] = 80.0  # pico atípico
    s = _serie(base, pd.date_range("2018-01-01", periods=40, freq="MS"))
    assert ins.es_anomalia(s, umbral=2.5, ventana=24) is True


def test_es_anomalia_falso_en_serie_estable():
    s = _serie([10.0, 10.1, 9.9] * 15, pd.date_range("2018-01-01", periods=45, freq="MS"))
    assert ins.es_anomalia(s, umbral=2.5, ventana=24) is False


def test_insights_serie_devuelve_estructura(idx):
    s = _serie(list(np.arange(1, 61, dtype=float)), idx)
    items = ins.insights_serie(s, nombre="test")
    assert isinstance(items, list) and len(items) >= 1
    for it in items:
        assert set(it.keys()) == {"texto", "tono"}
        assert it["tono"] in {"alza", "baja", "alerta", "neutro"}


def test_insights_serie_corta_vacia():
    s = _serie([1.0, 2.0], pd.date_range("2020-01-01", periods=2, freq="MS"))
    assert ins.insights_serie(s) == []
