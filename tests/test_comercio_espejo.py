"""
Tests de platec.comercio_espejo — apareo espejo y ajuste CIF/FOB.

Lo que se prueba de verdad es el AJUSTE CIF/FOB, que es la pieza que decide si la
discrepancia mide mala facturación o mide flete. Los casos están escritos contra
los modos de falla reales de esta medición: imponer un factor fijo donde los datos
dan otro, dejar que un reporte roto contamine la mediana de un país, y confundir
un FOB reportado con uno imputado.

Casi todo corre con paneles sintéticos: `discrepancia` acepta el panel inyectado,
así que no hace falta base ni red.
"""
import pandas as pd
import pytest

from platec import comercio_espejo as ce
from platec import data

COLUMNAS = ["year", "reporter_code", "partner_code", "flow_code",
            "primary_value", "fob_value", "cif_value"]

AR = ce.ARGENTINA
BR, AU = 76, 36


def _panel(filas) -> pd.DataFrame:
    return pd.DataFrame(filas, columns=COLUMNAS)


# ---------------------------------------------------------------------------
# El factor CIF/FOB
# ---------------------------------------------------------------------------
def test_el_factor_se_estima_por_pais_y_no_es_uno_solo_para_todos():
    """
    Brasil tiene frontera terrestre y Australia está del otro lado del mundo: su
    margen de flete no puede ser el mismo número. Es la razón de ser del módulo.
    """
    p = _panel([
        (2020, BR, AR, "M", 104.0, 100.0, 104.0),
        (2021, BR, AR, "M", 104.0, 100.0, 104.0),
        (2020, AU, AR, "M", 114.0, 100.0, 114.0),
        (2021, AU, AR, "M", 114.0, 100.0, 114.0),
    ])
    f = ce.factores_cif_fob(p)
    assert f[BR] == pytest.approx(1.04)
    assert f[AU] == pytest.approx(1.14)


def test_un_reporte_roto_no_contamina_el_factor_del_pais():
    """
    En los datos reales de 2022 hay un registro con un cociente cif/fob de 9.993%.
    El flete de un embarque no es cien veces su valor: es un error de reporte. Sin
    la cota, un solo registro así corre la mediana de todo un país.
    """
    p = _panel([
        (2019, BR, AR, "M", 104.0, 100.0, 104.0),
        (2020, BR, AR, "M", 104.0, 100.0, 104.0),
        (2021, BR, AR, "M", 100000.0, 1.0, 100000.0),   # basura: factor 100.000
    ])
    assert ce.factores_cif_fob(p)[BR] == pytest.approx(1.04)


def test_el_factor_global_se_calcula_no_se_supone():
    """El 10% de la literatura tiene que salir de los datos o no salir."""
    p = _panel([
        (2020, BR, AR, "M", 104.0, 100.0, 104.0),
        (2020, AU, AR, "M", 114.0, 100.0, 114.0),
    ])
    assert ce.factor_global(p) == pytest.approx(1.09)


def test_sin_ningun_pais_que_informe_ambas_valoraciones_no_hay_factores():
    p = _panel([(2020, BR, AR, "M", 104.0, None, 104.0)])
    assert ce.factores_cif_fob(p).empty


# ---------------------------------------------------------------------------
# La jerarquía del FOB
# ---------------------------------------------------------------------------
def _fob(fila, factores=None, glob=1.10):
    f = pd.Series(factores or {}, dtype="float64")
    return ce._a_fob(pd.Series(dict(zip(COLUMNAS, fila))), f, glob)


def test_el_fob_reportado_gana_y_no_se_estima_nada():
    valor, origen = _fob((2020, BR, AR, "M", 104.0, 100.0, 104.0), {BR: 1.04})
    assert valor == pytest.approx(100.0) and origen == "reportado"


def test_sin_fob_se_deflacta_el_cif_con_el_factor_del_pais():
    valor, origen = _fob((2020, BR, AR, "M", 104.0, None, 104.0), {BR: 1.04})
    assert valor == pytest.approx(100.0) and origen == "estimado (factor del país)"


def test_un_pais_sin_factor_propio_cae_a_la_mediana_global():
    valor, origen = _fob((2020, 999, AR, "M", 110.0, None, 110.0), {BR: 1.04}, glob=1.10)
    assert valor == pytest.approx(100.0) and origen == "estimado (mediana global)"


def test_sin_cif_ni_fob_se_usa_la_valoracion_primaria():
    valor, _ = _fob((2020, BR, AR, "M", 104.0, None, None), {BR: 1.04})
    assert valor == pytest.approx(100.0)


def test_sin_ningun_valor_el_fob_es_nan_y_no_cero():
    """Un cero se sumaría al agregado como si fuera comercio nulo. NaN no."""
    valor, origen = _fob((2020, BR, AR, "M", None, None, None))
    assert pd.isna(valor) and origen == "sin dato"


# ---------------------------------------------------------------------------
# El apareo y el signo
# ---------------------------------------------------------------------------
def test_canal_exportador_el_socio_declara_mas_de_lo_que_argentina_dice_haber_mandado():
    """Subfacturación de exportaciones: gap > 0 es salida de divisas."""
    p = _panel([
        (2020, AR, BR, "X", 100e6, 100e6, None),      # AR: exporté 100
        (2020, BR, AR, "M", 110e6, 110e6, None),      # BR: recibí 110
    ])
    d = ce.discrepancia(df=p)
    fila = d[d["canal"] == "exportador"].iloc[0]
    assert fila["gap"] == pytest.approx(10e6)
    assert fila["gap_pct"] == pytest.approx(10.0)


def test_canal_importador_argentina_declara_pagar_mas_de_lo_que_el_socio_mando():
    """Sobrefacturación de importaciones: gap > 0 también es salida de divisas."""
    p = _panel([
        (2020, AR, BR, "M", 110e6, 100e6, 110e6),     # AR: importé 100 FOB
        (2020, BR, AR, "X", 90e6, 90e6, None),        # BR: te mandé 90
    ])
    d = ce.discrepancia(df=p)
    fila = d[d["canal"] == "importador"].iloc[0]
    assert fila["gap"] == pytest.approx(10e6)


def test_el_ajuste_por_pais_puede_dar_vuelta_el_signo_frente_al_10_por_ciento_fijo():
    """
    EL TEST QUE JUSTIFICA EL MÓDULO. Brasil declara importar 107 (CIF) de una
    exportación argentina de 100 (FOB). Con el factor real de Brasil (~1,04) queda
    una discrepancia POSITIVA de ~2,9. Con el 10% fijo de la literatura quedaría
    NEGATIVA (~-2,7): el supuesto estándar sobrecorrige a un vecino con frontera
    terrestre y convierte una subfacturación en un superávit espejo inexistente.
    """
    p = _panel([
        (2020, AR, BR, "X", 100e6, 100e6, None),
        (2020, BR, AR, "M", 107e6, None, 107e6),          # solo CIF: hay que ajustar
        # los años que le dan a Brasil su factor propio (1,04)
        (2018, BR, AR, "M", 104e6, 100e6, 104e6),
        (2019, BR, AR, "M", 104e6, 100e6, 104e6),
    ])
    fila = ce.discrepancia(df=p)
    fila = fila[(fila["canal"] == "exportador") & (fila["anio"] == 2020)].iloc[0]

    assert fila["gap"] > 0, "con el factor propio de Brasil la discrepancia es positiva"
    assert fila["gap"] == pytest.approx(107e6 / 1.04 - 100e6, rel=1e-6)
    assert fila["origen_socio"] == "estimado (factor del país)"
    # el contrafáctico con el supuesto estándar
    assert 107e6 / 1.10 - 100e6 < 0, "el 10% fijo habría dado vuelta el signo"


def test_los_pares_chicos_se_descartan():
    """
    En un par que comercia diez millones al año, un embarque a caballo del cierre
    de ejercicio produce una discrepancia porcentual enorme que no dice nada.
    """
    p = _panel([
        (2020, AR, BR, "X", 10e6, 10e6, None),
        (2020, BR, AR, "M", 20e6, 20e6, None),
    ])
    assert ce.discrepancia(df=p, minimo_usd=50e6).empty
    assert not ce.discrepancia(df=p, minimo_usd=1e6).empty


def test_el_agregado_mundo_no_entra_al_apareo():
    """Sumar Mundo junto a los bilaterales contaría cada operación dos veces."""
    p = _panel([
        (2020, AR, ce.MUNDO, "X", 900e6, 900e6, None),
        (2020, AR, BR, "X", 100e6, 100e6, None),
        (2020, BR, AR, "M", 110e6, 110e6, None),
    ])
    d = ce.discrepancia(df=p)
    assert ce.MUNDO not in set(d["socio_code"])
    assert len(d) == 1


def test_un_flujo_sin_su_espejo_no_produce_fila():
    """Si el socio no reportó, no hay comparación: no se inventa una contra cero."""
    p = _panel([(2020, AR, BR, "X", 100e6, 100e6, None)])
    assert ce.discrepancia(df=p).empty


# ---------------------------------------------------------------------------
# Agregación
# ---------------------------------------------------------------------------
def test_la_cobertura_fob_pondera_por_valor_y_no_por_conteo():
    """
    Un socio grande con FOB imputado pesa más que uno chico con FOB reportado.
    Contar países le daría 50% a un agregado que en valor está casi todo estimado.
    """
    p = _panel([
        (2020, AR, BR, "X", 900e6, 900e6, None),
        (2020, BR, AR, "M", 940e6, None, 940e6),           # grande, estimado
        (2020, AR, AU, "X", 100e6, 100e6, None),
        (2020, AU, AR, "M", 110e6, 110e6, None),           # chico, reportado
    ])
    g = ce.por_anio(ce.discrepancia(df=p))
    fila = g[g["canal"] == "exportador"].iloc[0]
    assert fila["cobertura_fob"] == pytest.approx(0.10)
    assert fila["socios"] == 2


def test_el_agregado_viene_en_millones_de_dolares():
    p = _panel([
        (2020, AR, BR, "X", 100e6, 100e6, None),
        (2020, BR, AR, "M", 110e6, 110e6, None),
    ])
    fila = ce.por_anio(ce.discrepancia(df=p)).iloc[0]
    assert fila["gap"] == pytest.approx(10.0)          # 10 millones, no 10.000.000


def test_la_serie_anual_sale_indexada_por_fecha():
    """Para poder alinearla contra el resto de la base, que no es anual."""
    p = _panel([
        (2020, AR, BR, "X", 100e6, 100e6, None),
        (2020, BR, AR, "M", 110e6, 110e6, None),
        (2021, AR, BR, "X", 100e6, 100e6, None),
        (2021, BR, AR, "M", 120e6, 120e6, None),
    ])
    s = ce.serie_anual("exportador", df=p)
    assert isinstance(s.index, pd.DatetimeIndex)
    assert list(s.index.year) == [2020, 2021]
    assert s.iloc[1] == pytest.approx(20.0)


def test_sin_datos_no_explota_devuelve_vacio():
    vacio = _panel([])
    assert ce.discrepancia(df=vacio).empty
    assert ce.por_anio(ce.discrepancia(df=vacio)).empty


def test_un_socio_sin_nombre_se_muestra_por_su_codigo_m49():
    """No se pierde el dato por no tener el nombre en el diccionario."""
    assert ce.nombre_socio(BR) == "Brasil"
    assert ce.nombre_socio(999) == "M49 999"


# ---------------------------------------------------------------------------
# Contra los datos reales
# ---------------------------------------------------------------------------
requiere_espejo = pytest.mark.skipif(
    not data.DB_PATH.exists(),
    reason="requiere data/plataforma.db con trade_mirror (correr ingest_comtrade.py)")


@requiere_espejo
def test_el_factor_real_de_brasil_esta_muy_por_debajo_del_supuesto_de_la_literatura():
    """
    Regresión anclada a la realidad geográfica: Brasil comparte frontera y su
    flete es de un dígito bajo. Si este test empieza a fallar, o cambió la fuente
    o el filtro de factores absurdos dejó de funcionar.
    """
    p = ce.panel()
    if p.empty:
        pytest.skip("trade_mirror vacía")
    f = ce.factores_cif_fob(p)
    if BR not in f.index:
        pytest.skip("sin registros de Brasil con ambas valoraciones")
    assert 1.0 <= f[BR] < 1.08, f"factor de Brasil fuera de rango: {f[BR]}"
    assert f[BR] < ce.factor_global(p)


@requiere_espejo
def test_el_factor_global_real_queda_cerca_del_10_por_ciento_canonico():
    """
    Validación del supuesto estándar EN EL AGREGADO. Que dé cerca de 1,10 es lo
    que hace defendible usarlo como fallback; que varíe tanto por país es lo que
    hace indefendible usarlo país por país.
    """
    p = ce.panel()
    if p.empty:
        pytest.skip("trade_mirror vacía")
    assert 1.05 <= ce.factor_global(p) <= 1.15


# ---------------------------------------------------------------------------
# El cero que no es un dato
# ---------------------------------------------------------------------------
def test_un_fob_en_cero_no_es_un_fob_reportado():
    """
    REGRESIÓN. Comtrade devuelve `fobvalue = 0` —cero, no null— para los países que
    no calculan esa valoración. China informa su importación desde Argentina de 2020
    como cif = 6.814 millones y fob = 0. Tomar ese cero como un FOB legítimo llevaba
    la discrepancia del canal exportador a −27.000 millones de dólares: el 40% de
    las exportaciones argentinas, inventado por un cero.
    """
    valor, origen = _fob((2020, 156, AR, "M", 6814e6, 0.0, 6814e6), {156: 1.07})
    assert origen != "reportado"
    assert valor == pytest.approx(6814e6 / 1.07)


def test_un_cif_en_cero_tampoco_bloquea_la_valoracion_primaria():
    valor, origen = _fob((2020, BR, AR, "M", 104.0, 0.0, 0.0), {BR: 1.04})
    assert valor == pytest.approx(100.0) and origen.startswith("estimado")


def test_con_todo_en_cero_es_sin_dato_y_no_un_comercio_de_cero():
    valor, origen = _fob((2020, BR, AR, "M", 0.0, 0.0, 0.0))
    assert pd.isna(valor) and origen == "sin dato"


def test_el_cero_no_aparea_una_exportacion_real_contra_la_nada():
    """El caso completo, de punta a punta: sin el filtro, gap = -100% de lo exportado."""
    p = _panel([
        (2020, AR, 156, "X", 5244e6, 5244e6, None),
        (2020, 156, AR, "M", 6814e6, 0.0, 6814e6),
        (2018, 156, AR, "M", 107e6, 100e6, 107e6),   # le da a China su factor propio
    ])
    fila = ce.discrepancia(df=p)
    fila = fila[(fila["canal"] == "exportador") & (fila["anio"] == 2020)].iloc[0]
    assert fila["gap"] > 0, "el socio recibió más de lo que Argentina declaró mandar"
    assert fila["socio_declara"] > 6000e6


# ---------------------------------------------------------------------------
# Contraste contra la brecha cambiaria
# ---------------------------------------------------------------------------
def _panel_brecha(n_socios=20, n_anios=15, beta=0.0, ruido=1.0, seed=1):
    """
    Panel sintético con un efecto conocido de la brecha sobre la discrepancia.

    Sirve para dos cosas: verificar que el estimador recupera el beta que se le
    puso, y que bajo la nula el bootstrap no inventa significación.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    brechas = rng.uniform(0, 100, n_anios)
    filas = []
    for s in range(n_socios):
        efecto_socio = rng.normal(0, 5)          # el nivel propio de cada socio
        for i, anio in enumerate(range(2011, 2011 + n_anios)):
            filas.append({
                "anio": anio, "socio": f"S{s}", "canal": "exportador",
                "unidad": f"S{s}|exportador", "brecha": brechas[i],
                "gap_pct": efecto_socio + beta * brechas[i] + rng.normal(0, ruido),
            })
    return pd.DataFrame(filas)


def test_el_estimador_recupera_el_beta_que_se_le_puso():
    r = ce.contraste_brecha(df=_panel_brecha(beta=0.05), repl=99)
    assert r["beta"] == pytest.approx(0.05, abs=0.01)


def test_los_efectos_fijos_absorben_el_nivel_propio_de_cada_socio():
    """
    Es la razón de usar panel: el error del factor CIF/FOB imputado es constante en
    el tiempo para un mismo país, así que el efecto fijo se lo come. Un socio con un
    nivel absurdo no puede mover beta.
    """
    p = _panel_brecha(beta=0.05)
    p.loc[p["socio"] == "S0", "gap_pct"] += 500        # nivel disparatado, constante
    r = ce.contraste_brecha(df=p, repl=99)
    assert r["beta"] == pytest.approx(0.05, abs=0.01)


def test_bajo_la_nula_el_bootstrap_no_inventa_significacion():
    r = ce.contraste_brecha(df=_panel_brecha(beta=0.0, ruido=3.0), repl=299)
    assert r["p_wcb"] > 0.10


def test_el_p_del_bootstrap_nunca_es_cero():
    """
    (extremos + 1) / (repl + 1). Un p-valor de 0,0000 exacto es imposible de estimar
    con un bootstrap finito, y reportarlo sería decir que la evidencia es infinita.
    """
    r = ce.contraste_brecha(df=_panel_brecha(beta=0.5, ruido=0.2), repl=99)
    assert r["p_wcb"] == pytest.approx(1 / 100)


def test_el_agrupamiento_es_por_ano_y_no_por_observacion():
    """
    La brecha es común a todos los socios de un año: el panel mejora la estimación
    puntual pero NO multiplica los grados de libertad. Con un shock común anual, un
    error tratado como independiente entre observaciones sale absurdamente chico.

    Se compara el mismo estimador agrupando por año contra agrupando por observación
    —que es no agrupar— sobre los MISMOS datos: es una propiedad del estimador, no
    de un sorteo, así que no depende de la semilla.
    """
    import numpy as np
    rng = np.random.default_rng(3)
    p = _panel_brecha(beta=0.0, ruido=0.1)
    shock = {a: rng.normal(0, 8) for a in p["anio"].unique()}
    p["gap_pct"] += p["anio"].map(shock)

    y = p["gap_pct"].to_numpy()
    x = p["brecha"].to_numpy()
    u = p["unidad"].to_numpy()
    n_u = p["unidad"].nunique()

    _, se_anio, _ = ce._beta_t(y, x, u, p["anio"].to_numpy(), n_u)
    _, se_obs, _ = ce._beta_t(y, x, u, np.arange(len(p)), n_u)   # sin agrupar
    assert se_anio > 3 * se_obs, (
        f"agrupar por año tiene que ampliar el error: {se_anio:.4f} vs {se_obs:.4f}")


def test_una_muestra_corta_se_rechaza_en_vez_de_estimarse():
    """Con tres años no hay contraste posible: mejor un error que un beta con cara de dato."""
    with pytest.raises(ValueError, match="insuficiente"):
        ce.contraste_brecha(df=_panel_brecha(n_socios=2, n_anios=3), repl=9)


def test_el_contraste_es_determinista_a_igual_semilla():
    a = ce.contraste_brecha(df=_panel_brecha(beta=0.05), repl=99, seed=7)
    b = ce.contraste_brecha(df=_panel_brecha(beta=0.05), repl=99, seed=7)
    assert a["p_wcb"] == b["p_wcb"]


def test_la_fuente_de_brecha_desconocida_falla_temprano():
    with pytest.raises(ValueError, match="fuente desconocida"):
        ce.brecha_anual("dolar_soja")


@requiere_espejo
def test_el_estimador_propio_coincide_con_statsmodels():
    """
    El within + sándwich cluster está escrito a mano por velocidad (el bootstrap
    reestima mil veces). Que dé lo mismo que meter 100 dummies en statsmodels es lo
    que autoriza a usarlo.
    """
    sm = pytest.importorskip("statsmodels.api")
    d = ce.panel_con_brecha()
    d = d[d["canal"] == "exportador"]
    if len(d) < 100:
        pytest.skip("panel espejo insuficiente")

    du = pd.get_dummies(d["unidad"], drop_first=True).astype(float).reset_index(drop=True)
    X = sm.add_constant(pd.concat([d[["brecha"]].reset_index(drop=True), du], axis=1))
    m = sm.OLS(d["gap_pct"].reset_index(drop=True), X).fit(
        cov_type="cluster", cov_kwds={"groups": d["anio"].reset_index(drop=True)})

    beta, se, _ = ce._beta_t(d["gap_pct"].to_numpy(), d["brecha"].to_numpy(),
                             d["unidad"].to_numpy(), d["anio"].to_numpy(),
                             d["unidad"].nunique())
    assert beta == pytest.approx(m.params["brecha"], rel=1e-8)
    assert se == pytest.approx(m.bse["brecha"], rel=1e-6)


@requiere_espejo
def test_la_brecha_anual_tiene_los_picos_conocidos():
    """Anclaje a la realidad: 2016-2018 sin cepo, brecha ~0; 2022-23 con cepo, ~100%."""
    b = ce.brecha_anual("blue")
    assert b.loc[2017] < 10, "2017 no tuvo cepo: la brecha fue casi nula"
    assert b.loc[2023] > 60, "2023 estuvo en pleno cepo II"


def test_un_ano_con_pocos_socios_se_marca_provisorio():
    """
    Comtrade publica con rezago: en el último año faltan países, no falta comercio.
    En los datos reales 2025 aparea 51 socios contra ~70 de un año cerrado, y con ese
    cuarto faltante el agregado cambia de signo. Mostrarlo como el dato del año sería
    mentir por omisión.
    """
    filas = []
    for anio in range(2015, 2025):                      # años completos
        for s in range(20):
            filas.append((anio, AR, 100 + s, "X", 100e6, 100e6, None))
            filas.append((anio, 100 + s, AR, "M", 110e6, 110e6, None))
    for s in range(5):                                  # 2025: solo 5 socios
        filas.append((2025, AR, 100 + s, "X", 100e6, 100e6, None))
        filas.append((2025, 100 + s, AR, "M", 110e6, 110e6, None))

    g = ce.por_anio(ce.discrepancia(df=_panel(filas)))
    prov = dict(zip(g["anio"], g["provisorio"]))
    assert prov[2025] is True or prov[2025] == True     # noqa: E712
    assert not any(v for a, v in prov.items() if a < 2025), "los años completos no se marcan"


def test_el_umbral_de_provisorio_es_por_canal():
    """
    El canal exportador aparea más socios que el importador. Un umbral común
    castigaría al importador por existir, igual que contar meses castigaba a las
    series trimestrales en el comparador de gobiernos.
    """
    filas = []
    for anio in range(2018, 2024):
        for s in range(20):                             # 20 socios en el exportador
            filas.append((anio, AR, 100 + s, "X", 100e6, 100e6, None))
            filas.append((anio, 100 + s, AR, "M", 110e6, 110e6, None))
        for s in range(6):                              # 6 socios en el importador
            filas.append((anio, AR, 200 + s, "M", 110e6, 100e6, 110e6))
            filas.append((anio, 200 + s, AR, "X", 90e6, 90e6, None))
    g = ce.por_anio(ce.discrepancia(df=_panel(filas)))
    assert not g["provisorio"].any(), "todos los años son completos en su propio canal"
