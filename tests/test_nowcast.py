"""Tests de platec.nowcast — construcción de features y walk-forward.

Integración: dependen de la base poblada. Se saltan si no existe.
"""
import numpy as np
import pandas as pd
import pytest

from platec import data, nowcast

pytestmark = pytest.mark.skipif(
    not data.DB_PATH.exists(), reason="requiere data/plataforma.db (correr init_db + ingest)"
)


def test_construir_features_columnas():
    df = nowcast.construir_features()
    assert list(df.columns) == ["infl", "deval_of", "deval_ccl", "brecha", "infl_l1", "infl_l2"]
    assert not df.isna().any().any()      # dropna al final
    assert (df.index.day == 1).all()      # mensual, inicio de mes


def test_features_incluyen_target_y_predictores():
    df = nowcast.construir_features()
    assert "infl" in df.columns
    assert set(nowcast.FEATURES) <= set(df.columns)
    assert len(df) > 36  # muestra suficiente para el walk-forward (min_train=36)


def test_walk_forward_le_gana_al_naive():
    df = nowcast.construir_features()
    res = nowcast.evaluar_walk_forward(df, min_train=36)
    assert res.rmse_modelo > 0
    assert res.n_test > 0
    # el modelo debe superar (o al menos empatar) al random walk
    assert res.rmse_modelo <= res.rmse_naive
    assert set(res.coef.keys()) == set(nowcast.FEATURES)


def test_nowcast_actual_valor_razonable():
    df = nowcast.construir_features()
    pred = nowcast.nowcast_actual(df)
    assert isinstance(pred, float)
    # inflación mensual argentina en un rango plausible (no negativa extrema ni absurda)
    assert -5 < pred < 50
