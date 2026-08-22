"""Tests de platec.gobiernos — periodización, normalizaciones y agregados.

La lógica pura (períodos, etiquetado, cobertura, agregación) se prueba con series
sintéticas. Las normalizaciones por PBI se prueban contra la base real: su modo de
fallar no es tirar excepción sino devolver un número del orden de magnitud
equivocado, y eso solo se detecta contra valores conocidos de la economía.
"""
import numpy as np
import pandas as pd
import pytest

from platec import data, gobiernos as gob


# --- Periodización ---
def test_periodos_ordenados_y_sin_huecos():
    ps = gob.periodos()
    assert len(ps) == len(gob.GOBIERNOS)
    for anterior, siguiente in zip(ps, ps[1:]):
        # el traspaso de mando es el mismo instante: fin de uno == inicio del otro
        assert anterior.hasta == siguiente.desde


def test_mandato_en_curso_se_cierra_hoy():
    ultimo = gob.periodos()[-1]
    assert ultimo.en_curso
    assert ultimo.hasta <= pd.Timestamp.today().normalize()
    assert not any(p.en_curso for p in gob.periodos()[:-1])


def test_etiquetar_asigna_el_gobierno_correcto():
    idx = pd.to_datetime(["2005-06-01", "2010-06-01", "2017-06-01", "2021-06-01"])
    e = gob.etiquetar(pd.Series(1.0, index=idx))
    assert list(e) == ["N. Kirchner", "CFK I", "Macri", "A. Fernández"]


def test_etiquetar_deja_na_fuera_de_rango():
    e = gob.etiquetar(pd.Series(1.0, index=pd.to_datetime(["1980-01-01"])))
    assert e.isna().all()


# --- Cobertura ---
def _periodo(desde, hasta):
    return gob.Periodo("test", pd.Timestamp(desde), pd.Timestamp(hasta), False)


def test_cobertura_no_castiga_a_las_series_trimestrales():
    """
    El motivo de que la cobertura se mida por tramo y no por conteo de meses: una
    serie trimestral que cubre todo el mandato tiene un dato cada tres meses, y
    contarlos daría ~0,33 — por debajo del umbral, ocultando una serie completa.
    """
    p = _periodo("2016-01-01", "2020-01-01")
    trimestral = pd.Series(1.0, index=pd.date_range("2016-01-01", "2019-12-31", freq="QS"))
    mensual = pd.Series(1.0, index=pd.date_range("2016-01-01", "2019-12-31", freq="MS"))
    assert gob.cobertura(trimestral, p) > 0.95
    assert gob.cobertura(mensual, p) > 0.95


def test_cobertura_detecta_una_serie_que_solo_cubre_una_punta():
    p = _periodo("2016-01-01", "2020-01-01")
    punta = pd.Series(1.0, index=pd.date_range("2019-07-01", "2019-12-31", freq="MS"))
    assert gob.cobertura(punta, p) < 0.2


def test_cobertura_cero_con_menos_de_dos_observaciones():
    p = _periodo("2016-01-01", "2020-01-01")
    assert gob.cobertura(pd.Series(dtype="float64"), p) == 0.0
    assert gob.cobertura(pd.Series([1.0], index=pd.to_datetime(["2017-01-01"])), p) == 0.0


# --- Agregación ---
@pytest.fixture
def serie_larga():
    idx = pd.date_range("2004-01-01", "2026-01-01", freq="MS")
    return pd.Series(np.linspace(100, 200, len(idx)), index=idx)


def test_por_gobierno_agrega_como_se_le_pide(serie_larga):
    fin = gob.por_gobierno(serie_larga, como="fin")
    ini = gob.por_gobierno(serie_larga, como="inicio")
    cam = gob.por_gobierno(serie_larga, como="cambio")
    # serie creciente: el fin de cada mandato supera a su inicio y el cambio es positivo
    for g in ("CFK I", "Macri", "A. Fernández"):
        assert fin.loc[g, "valor"] > ini.loc[g, "valor"]
        assert cam.loc[g, "valor"] > 0
        assert np.isclose(cam.loc[g, "valor"], fin.loc[g, "valor"] - ini.loc[g, "valor"])


def test_por_gobierno_devuelve_nan_sin_cobertura_suficiente():
    """Un tramo corto no debe convertirse en el 'promedio del mandato'."""
    idx = pd.date_range("2019-09-01", "2019-12-01", freq="MS")   # 4 meses de Macri
    r = gob.por_gobierno(pd.Series(1.0, index=idx), como="promedio")
    assert np.isnan(r.loc["Macri", "valor"])
    assert r.loc["Macri", "cobertura"] < gob.COBERTURA_MINIMA


def test_var_anualizada_rechaza_series_no_positivas(serie_larga):
    s = serie_larga.copy()
    s.iloc[:] = -1.0
    assert gob.por_gobierno(s, como="var_anual").loc["Macri", "valor"] != gob.por_gobierno(
        serie_larga, como="var_anual").loc["Macri", "valor"]
    assert np.isnan(gob.por_gobierno(s, como="var_anual").loc["Macri", "valor"])


def test_como_invalido_falla_explicito(serie_larga):
    with pytest.raises(ValueError, match="`como` inválido"):
        gob.por_gobierno(serie_larga, como="mediana")


# --- Normalizaciones contra la base real ---
def test_pib_no_esta_cuadruplicado():
    """
    Regresión del bug que costó más caro: la serie de PIB viene etiquetada
    trimestral pero YA está anualizada, así que sumar los cuatro trimestres da
    4,3x y hunde todos los ratios a un cuarto. Se ancla contra magnitudes
    conocidas de la economía argentina, que es donde el error se ve.
    """
    recaudacion = gob.pct_pib(data.get_series("recaudacion_total"), "flujo")
    # la recaudación nacional ronda el 17-25% del PBI en todo el período;
    # con el bug caía a 4-6%.
    assert 15 < recaudacion.mean() < 28, f"recaudación fuera de rango: {recaudacion.mean()}"

    base = gob.pct_pib(data.get_series("base_monetaria"), "stock")
    # la base monetaria fue de ~10% del PBI en los 2000 y cayó a ~4% tras 2023
    assert 2 < base.min() < 8 and 6 < base.max() < 16


def test_pct_pib_rechaza_tipo_invalido():
    with pytest.raises(ValueError, match="stock.*flujo"):
        gob.pct_pib(data.get_series("base_monetaria"), tipo="promedio")


def test_pib_mensual_es_mensual_y_creciente():
    pib = gob.pib_mensual()
    assert pib.index.freqstr in ("MS", None) and len(pib) > 200
    assert pib.index.to_series().diff().dropna().dt.days.between(28, 31).all()
    # PIB nominal en un país con inflación: crece casi monótonamente año a año
    anual = pib.resample("YS").mean()
    assert (anual.diff().dropna() > 0).mean() > 0.9


# --- Tabla ---
def test_tabla_y_cobertura_tienen_la_misma_grilla():
    t, c = gob.tabla_comparativa(), gob.cobertura_matriz()
    assert t.shape == c.shape
    assert list(t.index) == list(c.index)
    assert list(t.columns) == list(c.columns) == [p.nombre for p in gob.periodos()]


def test_toda_celda_con_valor_tiene_cobertura_suficiente():
    """La invariante que sostiene la tabla: no hay número sin respaldo de cobertura."""
    t, c = gob.tabla_comparativa(), gob.cobertura_matriz()
    assert (c.values[t.notna().values] >= gob.COBERTURA_MINIMA).all()
