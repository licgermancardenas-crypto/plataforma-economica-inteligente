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


# ---------------------------------------------------------------------------
# Tipo de cambio real bilateral
# ---------------------------------------------------------------------------
def _tres(n=24, tc=100.0, p=100.0, pe=100.0):
    idx = pd.date_range("2020-01-01", periods=n, freq="MS")
    unos = lambda v: pd.Series([v] * n, index=idx, dtype=float)   # noqa: E731
    return unos(tc), unos(p), unos(pe)


def test_el_tcr_sube_cuando_sube_el_tipo_de_cambio_nominal():
    tc, p, pe = _tres()
    tc.iloc[12:] *= 2
    t = stats.tcr_bilateral(tc, p, pe, base=tc.index[0])
    assert t.iloc[0] == pytest.approx(100.0)
    assert t.iloc[-1] == pytest.approx(200.0)


def test_el_tcr_baja_cuando_sube_la_inflacion_local():
    """Más precios adentro con el mismo dólar es apreciación real: menos competitivo."""
    tc, p, pe = _tres()
    p.iloc[12:] *= 2
    t = stats.tcr_bilateral(tc, p, pe, base=tc.index[0])
    assert t.iloc[-1] == pytest.approx(50.0)


def test_el_tcr_sube_cuando_sube_la_inflacion_externa():
    """Es la razón de traer el CPI de EE.UU.: sin él este canal no existe."""
    tc, p, pe = _tres()
    pe.iloc[12:] *= 2
    t = stats.tcr_bilateral(tc, p, pe, base=tc.index[0])
    assert t.iloc[-1] == pytest.approx(200.0)


def test_sin_base_el_ancla_es_el_promedio_del_periodo():
    """Evita que la lectura dependa de qué mes se eligió como base."""
    tc, p, pe = _tres()
    tc.iloc[12:] *= 3
    t = stats.tcr_bilateral(tc, p, pe)
    assert t.mean() == pytest.approx(100.0)


def test_el_tcr_se_recorta_a_la_interseccion():
    """Un TCR en fechas donde falta un componente sería una invención."""
    tc, p, pe = _tres()
    pe = pe.iloc[6:]
    t = stats.tcr_bilateral(tc, p, pe)
    assert len(t) == len(pe)


def test_sin_solapamiento_falla_en_vez_de_devolver_vacio():
    tc, p, pe = _tres()
    pe.index = pe.index + pd.DateOffset(years=50)
    with pytest.raises(ValueError, match="solapan"):
        stats.tcr_bilateral(tc, p, pe)


def test_el_tc_deflactado_externo_no_toca_los_precios_locales():
    """
    ES LA PROPIEDAD QUE LO HACE USABLE EN EL PASS-THROUGH. Saca la inflación ajena
    sin meter la propia del lado derecho de la regresión.
    """
    tc, p, pe = _tres()
    p.iloc[12:] *= 5                       # la inflación local se dispara
    d = stats.tc_deflactado_externo(tc, pe)
    assert d.nunique() == 1, "los precios locales no deberían moverlo"
    pe.iloc[12:] *= 2
    d2 = stats.tc_deflactado_externo(tc, pe)
    assert d2.iloc[-1] == pytest.approx(d2.iloc[0] * 2)


@pytest.mark.skipif(not data.DB_PATH.exists(), reason="requiere data/plataforma.db")
def test_regresar_la_inflacion_contra_el_tcr_no_usa_el_dato_externo():
    """
    LA RAZÓN DE QUE EL TCR NO SEA UN REGRESOR DEL PASS-THROUGH. Como
    Δlog(TCR) = Δlog(e) + π* − π, la inflación queda a los dos lados. La prueba de
    que el coeficiente no dice nada: corriendo lo mismo SIN los precios externos, el
    resultado es prácticamente idéntico. La «relación» no depende del dato que se
    agregó, así que no es información: es la identidad contable.
    """
    sm = pytest.importorskip("statsmodels.api")
    ipc = data.get_series("ipc_general").dropna()
    us = data.get_series("cpi_eeuu").dropna()
    tc = data.get_series("usd_oficial").dropna().resample("MS").last()
    df = pd.concat({"ipc": ipc, "tc": tc, "us": us}, axis=1).dropna()
    if len(df) < 40:
        pytest.skip("muestra insuficiente")

    infl = np.log(df["ipc"]).diff() * 100

    def coef(serie_real):
        d = pd.concat({"y": infl, "x": (np.log(serie_real) * 100).diff()}, axis=1).dropna()
        return sm.OLS(d["y"], sm.add_constant(d["x"])).fit().params["x"]

    con_externo = coef(df["tc"] * df["us"] / df["ipc"])
    sin_externo = coef(df["tc"] / df["ipc"])
    assert con_externo == pytest.approx(sin_externo, abs=0.02), (
        f"con externo {con_externo:.3f}, sin externo {sin_externo:.3f}")


@pytest.mark.skipif(not data.DB_PATH.exists(), reason="requiere data/plataforma.db")
def test_el_tcr_real_reproduce_la_devaluacion_de_diciembre_2023():
    """Anclaje a un episodio conocido: el salto del 13/12/2023 fue de más del 50%."""
    ipc = data.get_series("ipc_general").dropna()
    us = data.get_series("cpi_eeuu").dropna()
    tc = data.get_series("usd_oficial").dropna().resample("MS").last()
    t = stats.tcr_bilateral(tc, ipc, us)
    if pd.Timestamp("2023-12-01") not in t.index:
        pytest.skip("la muestra no llega a diciembre de 2023")
    salto = t.loc["2023-12-01"] / t.loc["2023-11-01"] - 1
    assert salto > 0.50, f"el salto dio {salto:.1%}"
