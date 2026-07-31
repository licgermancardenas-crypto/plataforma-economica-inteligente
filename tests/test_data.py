"""Tests de platec.data — acceso a la base y alineación de frecuencias.

Integración: requieren data/plataforma.db poblada (init_db + ingest).
Se saltan automáticamente si la base no existe.
"""
import pandas as pd
import pytest

from platec import data

pytestmark = pytest.mark.skipif(
    not data.DB_PATH.exists(), reason="requiere data/plataforma.db (correr init_db + ingest)"
)


def test_catalogo_no_vacio():
    cat = data.catalogo()
    assert not cat.empty
    assert "series_id" in cat.columns
    assert "frequency" in cat.columns


def test_metadata_serie_conocida():
    meta = data.metadata("ipc_general")
    assert meta["series_id"] == "ipc_general"
    assert meta["frequency"] in ("D", "M", "Q")


def test_metadata_serie_desconocida_lanza():
    with pytest.raises(KeyError):
        data.metadata("no_existe_xyz")


def test_get_series_indexada_por_fecha():
    s = data.get_series("ipc_general")
    assert isinstance(s.index, pd.DatetimeIndex)
    assert s.index.is_monotonic_increasing
    assert s.dtype == "float64"
    assert s.attrs["series_id"] == "ipc_general"


def test_get_series_respeta_rango():
    s = data.get_series("ipc_general", start="2020-01-01", end="2020-12-31")
    assert s.index.min() >= pd.Timestamp("2020-01-01")
    assert s.index.max() <= pd.Timestamp("2020-12-31")


def test_get_frame_alinea_a_mensual():
    df = data.get_frame(["ipc_general", "usd_oficial"], freq="M")
    assert list(df.columns) == ["ipc_general", "usd_oficial"]
    # índice mensual (inicio de mes)
    assert (df.index.day == 1).all()
    assert not df.dropna().empty


def test_get_frame_downsample_diaria_a_trimestral():
    # usd_oficial es diaria -> debe agregarse a trimestral sin explotar
    df = data.get_frame(["usd_oficial"], freq="Q", how="mean")
    assert df.index.is_monotonic_increasing
    assert not df.dropna().empty
