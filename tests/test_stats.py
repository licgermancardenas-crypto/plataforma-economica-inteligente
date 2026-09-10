"""Tests de platec.stats — transformaciones puras sobre series."""
import numpy as np
import pandas as pd
import pytest

from platec import data, stats


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


# ---------------------------------------------------------------------------
# log_dif con cortes: cuando el índice se redefine, la variación no es un dato
# ---------------------------------------------------------------------------
def _serie_con_canje():
    """
    Una serie tipo riesgo país: nivel alto, un día en que el índice se recompone y
    cae a un décimo, y después nivel bajo. El salto NO es un movimiento de precio.
    """
    idx = pd.date_range("2005-06-08", periods=8, freq="D")
    return pd.Series([6600.0, 6650.0, 6600.0, 800.0, 810.0, 800.0, 790.0, 800.0],
                     index=idx)


def test_log_dif_sin_cortes_es_una_log_diferencia_comun():
    s = pd.Series([100.0, 110.0, 121.0])
    d = stats.log_dif(s)
    assert pd.isna(d.iloc[0])
    assert d.iloc[1] == pytest.approx(np.log(1.1) * 100)
    assert d.iloc[2] == pytest.approx(np.log(1.1) * 100)


def test_el_retorno_que_cruza_el_corte_queda_en_nan_y_no_en_cero():
    """
    Un cero afirmaría que la serie no se movió, que es falso: lo que pasa es que el
    dato no existe, porque une dos objetos distintos.
    """
    s = _serie_con_canje()
    d = stats.log_dif(s, cortes=["2005-06-11"])
    assert pd.isna(d.loc["2005-06-11"])
    assert d.loc["2005-06-11"] != 0


def test_los_dias_vecinos_al_corte_conservan_su_retorno():
    """Se rompe una variación, no el tramo: el nivel de esos días es correcto."""
    s = _serie_con_canje()
    d = stats.log_dif(s, cortes=["2005-06-11"])
    assert d.loc["2005-06-12"] == pytest.approx(np.log(810 / 800) * 100)
    assert d.loc["2005-06-10"] == pytest.approx(np.log(6600 / 6650) * 100)


def test_el_corte_saca_el_artefacto_del_desvio():
    s = _serie_con_canje()
    crudo = stats.log_dif(s).std()
    limpio = stats.log_dif(s, cortes=["2005-06-11"]).std()
    assert limpio < crudo / 5, "el salto del canje dominaba el desvío"


def test_una_fecha_de_corte_que_no_esta_en_el_indice_no_rompe():
    """La lista de recomposiciones es fija; una submuestra puede no contenerlas todas."""
    s = _serie_con_canje()
    d = stats.log_dif(s, cortes=["1999-01-01", "2005-06-11"])
    assert pd.isna(d.loc["2005-06-11"])
    assert d.notna().sum() == len(s) - 2      # el primero (diff) y el corte


def test_la_lista_de_recomposiciones_cubre_los_dos_canjes():
    """
    Documental: si alguien saca una fecha, el test dice cuáles son y por qué están.
    2005-06-13 es la liquidación del canje I; 2020-09-10 la del canje 2020.
    """
    assert "2005-06-13" in stats.RECOMPOSICIONES_EMBI
    assert "2020-09-10" in stats.RECOMPOSICIONES_EMBI
    assert all(isinstance(m, str) and m for m in stats.RECOMPOSICIONES_EMBI.values()), \
        "cada fecha tiene que traer el evento que la justifica"


@pytest.mark.skipif(not data.DB_PATH.exists(), reason="requiere data/plataforma.db")
def test_el_salto_de_las_paso_2019_sobrevive_a_la_limpieza():
    """
    EL TEST QUE JUSTIFICA LISTAR LAS FECHAS A MANO. El 12/08/2019, el lunes después
    de las PASO, el riesgo país salta +52% en un día: estadísticamente es tan extremo
    como una recomposición del índice y es el dato más informativo de toda la serie.
    Una regla automática por z-score borraría los dos. La lista es conocimiento del
    dominio, no un test estadístico.
    """
    r = data.get_series("riesgo_pais").dropna()
    d = stats.log_dif(r, cortes=stats.RECOMPOSICIONES_EMBI)
    assert d.loc["2019-08-12"] > 40, "se borró un movimiento de mercado real"
    assert pd.isna(d.loc["2020-09-10"]), "no se anuló la recomposición de 2020"
