"""
Tests de platec.firmas_sinteticas — generador de estados contables sintéticos.

Lo que se prueba de verdad es que el dataset NO SEA TRIVIAL. Un generador ingenuo
produce datos que cualquier detector resuelve por la vía equivocada: balances que no
cierran, montos uniformes que violan Benford, o maniobras tan marcadas que se ven a
ojo. Cada test acá corresponde a una de esas formas de arruinar el dataset.

También se protege el aislamiento: nada de esto puede terminar al lado de un dato
real, y el módulo no persiste nada.
"""
import json

import numpy as np
import pandas as pd
import pytest

from platec import firmas_sinteticas as fs


@pytest.fixture(scope="module")
def panel():
    """Panel con la prevalencia por defecto: para las propiedades generales."""
    return fs.generar(n_firmas=400, ejercicios=4, semilla=7)


@pytest.fixture(scope="module")
def panel_tipologias():
    """
    Panel con prevalencia alta, SOLO para medir la firma de cada tipología.

    Con la prevalencia realista quedan dos o tres firmas por tipología y la mediana
    la decide en qué sectores cayeron, no la maniobra. La prevalencia es un
    parámetro del generador, no una propiedad del fenómeno: para caracterizar una
    maniobra hace falta señal, para evaluar un detector hace falta realismo.
    """
    return fs.generar(n_firmas=1400, ejercicios=4, semilla=13, prevalencia=0.42)


def _normalizado(d: pd.DataFrame, cals) -> pd.Series:
    """
    salarios/ingresos de cada fila, dividido por la participación salarial de SU
    sector. Controla la composición: sin esto se compara un puñado de firmas de
    Enseñanza (94% de nómina) contra otro de Minas (29%) y no la maniobra.
    """
    esperado = d["sector"].map(lambda s: cals[s].participacion_salarial)
    return (d["salarios"] / d["ingresos"]) / esperado


# ---------------------------------------------------------------------------
# Que el dataset no sea trivial
# ---------------------------------------------------------------------------
def test_el_balance_cierra_en_todas_las_filas(panel):
    """
    Activo = Pasivo + Patrimonio. Si no articula, un detector encuentra la maniobra
    por la vía equivocada: separa las firmas por un error de construcción, no por su
    comportamiento.
    """
    assert fs.articula(panel)


def test_los_montos_cumplen_la_ley_de_benford(panel):
    """
    Los datos contables reales siguen Benford, y su desviación es en sí misma un
    detector forense clásico. Un generador con `uniform()` la viola y vuelve trivial
    el problema. El umbral de 0,015 es la convención de "no conformidad".
    """
    for columna in ("ingresos", "activo", "salarios"):
        mad = fs.desvio_benford(panel[columna])
        assert mad < 0.015, f"{columna} no conforma a Benford: MAD={mad:.4f}"


def test_benford_esperado_suma_uno():
    assert fs.benford_esperado().sum() == pytest.approx(1.0)
    assert fs.benford_esperado().loc[1] == pytest.approx(0.30103, abs=1e-4)


def test_el_primer_digito_ignora_ceros_y_signos():
    s = pd.Series([0.00123, -45.6, 900.0, 0.0, np.nan])
    d = fs.primer_digito(s)
    assert d.sum() == pytest.approx(1.0)
    assert d.loc[1] > 0 and d.loc[4] > 0 and d.loc[9] > 0


def test_la_prevalencia_por_defecto_es_baja(panel):
    """
    En AML la prevalencia real es del orden de 1 en 1.000. Un dataset balanceado
    convierte un problema de detección en uno de clasificación fácil que no se
    parece a nada.
    """
    marcadas = panel.groupby("firma")["tipologia"].first().ne("limpia").mean()
    assert marcadas < 0.10


def test_la_prevalencia_pedida_se_respeta():
    d = fs.generar(n_firmas=200, ejercicios=2, semilla=3, prevalencia=0.10)
    marcadas = d.groupby("firma")["tipologia"].first().ne("limpia").mean()
    assert marcadas == pytest.approx(0.10, abs=0.02)


def test_una_prevalencia_imposible_falla_temprano():
    with pytest.raises(ValueError, match="prevalencia"):
        fs.generar(n_firmas=10, prevalencia=1.5)


# ---------------------------------------------------------------------------
# Las tipologías
# ---------------------------------------------------------------------------
def _ratio(d, num, den):
    return (d[num] / d[den]).median()


def test_la_pantalla_factura_sin_nomina(panel_tipologias):
    """La sociedad pantalla no se delata por facturar mucho, sino por facturar sin con qué."""
    d = panel_tipologias
    p = d[(d["tipologia"] == "pantalla") & d["maniobra_activa"]]
    limpias = d[~d["maniobra_activa"]]
    assert _ratio(p, "salarios", "ingresos") < _ratio(limpias, "salarios", "ingresos") / 5
    assert _ratio(p, "activo_fijo", "ingresos") < _ratio(limpias, "activo_fijo", "ingresos") / 3


def test_el_negocio_de_efectivo_tiene_caja_desalineada(panel_tipologias):
    d = panel_tipologias
    e = d[(d["tipologia"] == "efectivo") & d["maniobra_activa"]]
    limpias = d[~d["maniobra_activa"]]
    assert _ratio(e, "caja", "ingresos") > _ratio(limpias, "caja", "ingresos") * 2


def test_la_subfacturacion_comprime_el_margen(panel_tipologias):
    """
    La exportación omitida nunca entra a los libros, pero el costo de producirla sí:
    el margen declarado cae. Es una firma REAL de la maniobra.

    Ojo con el supuesto que hay detrás: el modelo omite ingresos y deja los costos
    en los libros. Una firma que además maneje los costos correspondientes por fuera
    mostraría un margen menos comprimido, así que este canal está en el extremo
    detectable del rango.
    """
    d, cals = panel_tipologias, fs.calibraciones()
    esp = lambda s: s["sector"].map(lambda x: cals[x].margen_operativo)     # noqa: E731
    m = lambda s: ((s["resultado_operativo"] / s["ingresos"]) / esp(s)).median()  # noqa: E731
    sub = d[(d["tipologia"] == "subfacturacion_exportaciones") & d["maniobra_activa"]]
    assert m(sub) < m(d[~d["maniobra_activa"]]) * 0.85


def test_la_subfacturacion_no_deforma_la_huella_operativa(panel_tipologias):
    """
    Y acá está el límite de lo que el balance puede decir: el subfacturador tiene la
    nómina de su sector. Un margen bajo lo comparte con cualquier empresa que
    simplemente gana poco, así que el estado contable **no identifica** la maniobra
    — sólo la señala. Lo que la identifica es comparar contra lo que declara la
    contraparte, que es lo que hace `comercio_espejo`.
    """
    d, cals = panel_tipologias, fs.calibraciones()
    limpias = _normalizado(d[~d["maniobra_activa"]], cals).median()
    sub = _normalizado(d[(d["tipologia"] == "subfacturacion_exportaciones")
                         & d["maniobra_activa"]], cals).median()
    pantalla = _normalizado(d[(d["tipologia"] == "pantalla")
                              & d["maniobra_activa"]], cals).median()
    assert abs(sub / limpias - 1) < 0.25
    assert abs(pantalla / limpias - 1) > 4 * abs(sub / limpias - 1)


def test_la_sobrefacturacion_se_delata_por_la_intensidad_importadora(panel_tipologias):
    """
    El margen comprimido no alcanza para distinguirla; lo que la separa es importar
    mucho más que sus pares. Fue el defecto que destapó la primera versión: con la
    maniobra repartida al azar entre firmas que apenas importaban, movía el margen
    de 0,96 a 0,95 y no significaba nada.
    """
    d = panel_tipologias
    sob = d[(d["tipologia"] == "sobrefacturacion_importaciones") & d["maniobra_activa"]]
    limpias = d[~d["maniobra_activa"]]
    assert _ratio(sob, "importaciones", "otros_costos") > \
        _ratio(limpias, "importaciones", "otros_costos") * 2.5


def test_las_maniobras_comerciales_van_a_firmas_que_pueden_hacerlas(panel_tipologias):
    """No se puede sobrefacturar importaciones sin importar, ni subfacturar sin exportar."""
    d = panel_tipologias.groupby("firma").first()
    exp = d[d["tipologia"] == "subfacturacion_exportaciones"]["exportador"]
    imp = d[d["tipologia"] == "sobrefacturacion_importaciones"]["importador"]
    limpias = d[d["tipologia"] == "limpia"]
    assert exp.min() > limpias["exportador"].median()
    assert imp.min() > limpias["importador"].median()


# ---------------------------------------------------------------------------
# El puente con el resultado macro
# ---------------------------------------------------------------------------
def test_la_brecha_calibra_la_discrepancia_contra_el_beta_estimado():
    """
    El panel sintético tiene que reproducir el beta que `comercio_espejo` estimó
    sobre datos reales: +0,0589 puntos de discrepancia por punto de brecha. Es lo
    que convierte al generador en un puente micro-macro y no en un simulador suelto.
    """
    # La prevalencia tiene que estar por encima del umbral de factibilidad. Ese umbral
    # subió al solapar los soportes de intensidad comercial: ahora las firmas limpias
    # también exportan, así que hacen falta más manipuladoras para alcanzar la misma
    # participación en el valor exportado. El share mínimo no cambió; sí cuántas firmas
    # hacen falta para llegar a él.
    for brecha in (25.0, 50.0, 100.0):
        d = fs.generar(n_firmas=1500, ejercicios=3, semilla=5,
                       prevalencia=0.65, brecha=brecha)
        objetivo = fs.BETA_EXPORTADOR * brecha / 100
        assert d.attrs["calibrado"], f"no factible a brecha {brecha}"
        assert fs.discrepancia_exportadora(d) == pytest.approx(objetivo, rel=0.15)


def test_la_sobrefacturacion_NO_escala_con_la_brecha():
    """
    EL HALLAZGO MACRO, ENCODEADO. El contraste da beta = +0,009 con p = 0,68 en el
    canal importador: un cero limpio. Sobrefacturar exige acceso al dólar oficial,
    que es lo que el cepo raciona; subfacturar no exige permiso de nadie. Que el
    generador hiciera crecer las dos maniobras con la brecha contradiría la
    evidencia de la propia plataforma.
    """
    sin, con = (fs.generar(n_firmas=800, ejercicios=3, semilla=5,
                           prevalencia=0.20, brecha=b) for b in (0.0, 120.0))
    f = lambda d: d[(d["tipologia"] == "sobrefacturacion_importaciones")   # noqa: E731
                    & d["maniobra_activa"]]["desvio_maniobra"].median()
    assert f(sin) == pytest.approx(f(con), rel=1e-9)


def test_sin_brecha_no_se_calibra_nada():
    d = fs.generar(n_firmas=300, ejercicios=2, semilla=5, prevalencia=0.20, brecha=0.0)
    assert d.attrs["brecha"] == 0.0
    assert fs.discrepancia_exportadora(d) > 0     # hay maniobra, pero sin objetivo


def test_una_brecha_negativa_falla_temprano():
    with pytest.raises(ValueError, match="brecha"):
        fs.generar(n_firmas=10, brecha=-5.0)


def test_la_maniobra_empieza_en_un_ejercicio_y_no_siempre_en_el_primero(panel_tipologias):
    """Una anomalía lo es contra el propio pasado de la firma: hace falta que haya pasado."""
    marcadas = panel_tipologias[panel_tipologias["tipologia"] != "limpia"]
    if marcadas.empty:
        pytest.skip("sin firmas marcadas")
    por_firma = marcadas.groupby("firma")["maniobra_activa"]
    assert (~por_firma.all()).any(), "ninguna firma tiene ejercicios previos limpios"


def test_las_firmas_limpias_nunca_tienen_maniobra_activa(panel):
    assert not panel.loc[panel["tipologia"] == "limpia", "maniobra_activa"].any()


def test_toda_tipologia_generada_esta_documentada(panel):
    assert set(panel["tipologia"]).issubset(fs.TIPOLOGIAS)
    assert all(v.descripcion for v in fs.TIPOLOGIAS.values())


def test_toda_maniobra_cita_su_indicador_de_origen():
    """
    La cita ata cada tipología a un indicador publicado en vez de a la intuición de
    quien escribió el generador. Si una maniobra no puede citar nada, probablemente
    no exista.
    """
    for nombre, tip in fs.TIPOLOGIAS.items():
        if nombre == "limpia":
            continue
        assert "GAFI" in tip.fuente or "GAFILAT" in tip.fuente, nombre


# ---------------------------------------------------------------------------
# Calibración contra datos reales
# ---------------------------------------------------------------------------
def test_las_firmas_limpias_respetan_la_participacion_salarial_de_su_sector(panel):
    """
    Es lo que hace que la anomalía signifique algo: sin la estructura real del
    sector, "poca nómina" no tiene contra qué medirse.
    """
    cals = fs.calibraciones()
    limpias = panel[~panel["maniobra_activa"]]
    for sector, g in limpias.groupby("sector"):
        if len(g) < 25:
            continue
        observado = _ratio(g, "salarios", "ingresos")
        esperado = cals[sector].participacion_salarial
        assert observado == pytest.approx(esperado, rel=0.25), sector


def test_los_sectores_salen_del_archivo_de_ratios(panel):
    assert set(panel["sector"]).issubset(set(fs.calibraciones()))


def test_sin_el_archivo_de_ratios_el_error_dice_qué_correr(tmp_path):
    with pytest.raises(FileNotFoundError, match="ingest_ratios_sectoriales"):
        fs.calibraciones(tmp_path / "no_existe.json")


def test_el_archivo_de_ratios_declara_su_fuente():
    """Es el único dato REAL que toca este módulo: tiene que decir de dónde salió."""
    j = json.loads(fs.RATIOS.read_text(encoding="utf-8"))
    assert "INDEC" in j["fuente"]
    assert j["ultimo_dato"] and len(j["sectores"]) >= 5


# ---------------------------------------------------------------------------
# Aislamiento: nada sintético puede terminar al lado de un dato real
# ---------------------------------------------------------------------------
def test_es_determinista_a_igual_semilla():
    """
    La reproducibilidad se consigue guardando un entero, no un dataset. Por eso el
    módulo no persiste nada y ninguna fila sintética puede llegar a la base.
    """
    a = fs.generar(n_firmas=60, ejercicios=2, semilla=11)
    b = fs.generar(n_firmas=60, ejercicios=2, semilla=11)
    pd.testing.assert_frame_equal(a, b)


def test_semillas_distintas_dan_paneles_distintos():
    a = fs.generar(n_firmas=60, ejercicios=2, semilla=11)
    b = fs.generar(n_firmas=60, ejercicios=2, semilla=12)
    assert not a["ingresos"].equals(b["ingresos"])


def test_el_panel_viene_marcado_como_sintetico(panel):
    assert panel.attrs["sintetico"] is True
    assert panel.attrs["semilla"] == 7


def test_las_firmas_no_imitan_a_ninguna_empresa_real(panel):
    """
    Restricción de diseño, no un detalle: identificadores neutros, sin nombre ni
    CUIT. Nada de lo que sale de acá puede pasar por una presentación genuina.
    """
    assert panel["firma"].str.fullmatch(r"SINT-\d{4}").all()
    assert not {"nombre", "razon_social", "cuit"} & set(panel.columns)


def test_el_modulo_no_escribe_nada_en_disco(tmp_path, monkeypatch):
    """Se genera en memoria: no hay tabla, no hay snapshot, no hay fila persistida."""
    monkeypatch.chdir(tmp_path)
    antes = set(tmp_path.iterdir())
    fs.generar(n_firmas=30, ejercicios=2, semilla=5)
    assert set(tmp_path.iterdir()) == antes


def test_la_calibracion_avisa_cuando_no_es_factible():
    """
    Con pocas firmas subfacturadoras ninguna intensidad admisible alcanza el objetivo.
    No es un bug: es una restricción económica. Antes se topeaba en silencio y salían
    firmas con margen operativo NEGATIVO, que es un estado contable absurdo.
    """
    # n y prevalencia suficientes para que HAYA subfacturadoras —con seis tipologías,
    # el 2% de 500 firmas a veces no deja ninguna— pero por debajo del umbral que
    # hace factible el objetivo.
    d = fs.generar(n_firmas=1000, ejercicios=3, semilla=7, prevalencia=0.04, brecha=100.0)
    assert d.attrs["calibrado"] is False
    assert d.attrs["discrepancia_lograda"] < d.attrs["objetivo_discrepancia"]

    sub = d[(d["tipologia"] == "subfacturacion_exportaciones") & d["maniobra_activa"]]
    assert not sub.empty, "el caso a proteger necesita al menos una subfacturadora"
    assert (sub["resultado_operativo"] / sub["ingresos"]).median() > 0, \
        "una firma con margen negativo delata la maniobra por la vía equivocada"


def test_con_prevalencia_suficiente_la_calibracion_se_logra():
    d = fs.generar(n_firmas=1500, ejercicios=3, semilla=7, prevalencia=0.65, brecha=100.0)
    assert d.attrs["calibrado"] is True
    assert d.attrs["discrepancia_lograda"] == pytest.approx(
        d.attrs["objetivo_discrepancia"], rel=0.15)


def test_el_share_minimo_es_una_implicancia_del_beta_macro():
    """
    Si se omite el 5,9% de las exportaciones y ninguna firma omite más del 60% de las
    suyas, al menos el 9,8% del valor exportado pasa por manipuladores. Es aritmética
    sobre el beta estimado, no un parámetro del simulador.
    """
    assert fs.share_exportador_minimo(100.0) == pytest.approx(0.0589 / 0.60, rel=1e-6)
    assert fs.share_exportador_minimo(50.0) < fs.share_exportador_minimo(100.0)
    assert fs.share_exportador_minimo(100.0, intensidad_maxima=1.0) == pytest.approx(0.0589)


def test_el_umbral_teorico_coincide_con_el_empirico():
    """
    La prevalencia a la que la calibración se vuelve factible tiene que ser aquella en
    que los manipuladores alcanzan el share mínimo. Que teoría y simulación coincidan
    es lo que hace creíble a las dos.
    """
    minimo = fs.share_exportador_minimo(100.0)
    d = fs.generar(n_firmas=1500, ejercicios=3, semilla=7, prevalencia=0.65, brecha=100.0)
    sub = d[d["tipologia"] == "subfacturacion_exportaciones"]
    share = sub["exportaciones"].sum() / d["exportaciones"].sum()
    assert share >= minimo * 0.95 and d.attrs["calibrado"]


def test_una_intensidad_maxima_imposible_falla():
    with pytest.raises(ValueError, match="intensidad"):
        fs.share_exportador_minimo(100.0, intensidad_maxima=0.0)


# ---------------------------------------------------------------------------
# Las tipologías traídas de los indicadores de GAFI
# ---------------------------------------------------------------------------
def test_la_fachada_factura_por_encima_de_su_capacidad_instalada(panel_tipologias):
    """
    LA VARIANTE DIFÍCIL. La operación es real: nómina y activo fijo quedan donde los
    puso el sector. Lo que sobra es facturación, así que la firma produce más de lo
    que su capacidad explica y su margen mejora —el dinero inyectado no tiene costo—.
    """
    d = panel_tipologias
    f = d[(d["tipologia"] == "fachada") & d["maniobra_activa"]]
    limpias = d[~d["maniobra_activa"]]
    assert _ratio(f, "ingresos", "activo_fijo") > _ratio(limpias, "ingresos", "activo_fijo")
    assert _ratio(f, "resultado_operativo", "ingresos") > \
        _ratio(limpias, "resultado_operativo", "ingresos")


def test_la_fachada_es_mucho_menos_visible_que_la_pantalla(panel_tipologias):
    """
    Es la razón de haberla agregado. La pantalla no tiene cuerpo y salta a la vista;
    la fachada tiene empleados y planta de verdad, así que no hay anomalía
    estructural que buscar. Un dataset con sólo pantallas sobreestima cualquier
    detector.
    """
    d, cals = panel_tipologias, fs.calibraciones()
    limpias = _normalizado(d[~d["maniobra_activa"]], cals).median()
    fachada = _normalizado(d[(d["tipologia"] == "fachada") & d["maniobra_activa"]], cals).median()
    pantalla = _normalizado(d[(d["tipologia"] == "pantalla") & d["maniobra_activa"]], cals).median()

    # En términos absolutos y no de un cociente: la pantalla queda casi sin nómina,
    # la fachada la conserva en dos tercios de lo normal de su sector. Las dos se
    # desvían, pero sólo una lo hace de una forma que salta a la vista.
    assert pantalla / limpias < 0.20, "la pantalla tiene que quedar casi sin nómina"
    assert 0.45 < fachada / limpias < 0.85, "la fachada conserva su nómina real"


def test_las_compras_desproporcionadas_se_financian_con_deuda(panel_tipologias):
    """Compró por encima de lo que su operación sostiene, y no lo pagó con resultados."""
    d = panel_tipologias
    c = d[(d["tipologia"] == "compras_desproporcionadas") & d["maniobra_activa"]]
    limpias = d[~d["maniobra_activa"]]
    assert _ratio(c, "pasivo", "patrimonio") > _ratio(limpias, "pasivo", "patrimonio") * 3
    assert _ratio(c, "activo_fijo", "ingresos") > _ratio(limpias, "activo_fijo", "ingresos") * 2


def test_la_entidad_reactivada_no_se_distingue_en_corte_transversal(panel_tipologias):
    """
    PROPIEDAD DESEADA. Su anomalía es la TRAYECTORIA, no el nivel: mirando un solo
    ejercicio es una empresa cualquiera. Es lo que obliga a un detector a usar la
    historia de la firma y no una foto.
    """
    d, cals = panel_tipologias, fs.calibraciones()
    limpias = _normalizado(d[~d["maniobra_activa"]], cals).median()
    nueva = _normalizado(d[(d["tipologia"] == "nueva_alto_volumen")
                           & d["maniobra_activa"]], cals).median()
    assert abs(nueva / limpias - 1) < 0.15


def test_la_entidad_reactivada_salta_despues_de_la_latencia(panel_tipologias):
    """Y en la trayectoria sí se ve: el salto es de un orden de magnitud."""
    d = panel_tipologias.sort_values(["firma", "ejercicio"]).copy()
    d["crec"] = d.groupby("firma")["ingresos"].pct_change()
    maximo = d.groupby(["firma", "tipologia"])["crec"].max().reset_index()
    nueva = maximo[maximo["tipologia"] == "nueva_alto_volumen"]["crec"].median()
    limpia = maximo[maximo["tipologia"] == "limpia"]["crec"].median()
    assert nueva > 5 * limpia
    assert nueva < 100, "un salto de dos órdenes se detecta a ojo y vuelve trivial el caso"


def test_la_latencia_ocurre_antes_del_salto_y_no_al_reves():
    """Sin ejercicios latentes previos no hay nada que observar."""
    d = fs.generar(n_firmas=600, ejercicios=4, semilla=13, prevalencia=0.42)
    nuevas = d[d["tipologia"] == "nueva_alto_volumen"]
    if nuevas.empty:
        pytest.skip("sin firmas reactivadas en esta semilla")
    por_firma = nuevas.groupby("firma")["maniobra_activa"]
    assert not por_firma.first().any(), "alguna arranca ya reactivada"
    assert por_firma.last().all(), "alguna nunca se reactiva"
