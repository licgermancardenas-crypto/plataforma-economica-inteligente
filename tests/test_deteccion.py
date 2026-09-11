"""
Tests de platec.deteccion — el detector sobre el panel sintético.

Lo que se protege acá no es que el detector ande bien: es que **si anda demasiado
bien, alguien se entere**. Un PR-AUC alto en un problema de detección con prevalencia
del 2% es un diagnóstico sobre el dataset antes que un logro, y así se encontró la
fuga de los soportes disjuntos que tenía el generador.
"""
import numpy as np
import pandas as pd
import pytest

from platec import deteccion as det
from platec import firmas_sinteticas as fs

pytest.importorskip("sklearn")


@pytest.fixture(scope="module")
def cals():
    return fs.calibraciones()


@pytest.fixture(scope="module")
def panel():
    return fs.generar(n_firmas=3000, ejercicios=4, semilla=21, prevalencia=0.04,
                      brecha=100.0)


@pytest.fixture(scope="module")
def resultado(panel, cals):
    return det.evaluar(panel, cals)


# ---------------------------------------------------------------------------
# Que no haya fuga de etiqueta
# ---------------------------------------------------------------------------
def test_las_caracteristicas_no_contienen_la_etiqueta(panel, cals):
    """
    `desvio_maniobra` es cero exactamente en toda firma limpia: un modelo que la
    viera resolvería el problema por definición, no por detección.
    """
    X = det.caracteristicas(panel, cals)
    for prohibida in det.COLUMNAS_PROHIBIDAS:
        assert not any(prohibida in c for c in X.columns), prohibida


def test_las_caracteristicas_salen_solo_de_lo_observable(panel, cals):
    """Todo lo que usa el detector se puede calcular de un balance y un resultado."""
    X = det.caracteristicas(panel, cals)
    assert len(X) == panel["firma"].nunique(), "una fila por firma, no por ejercicio"
    assert X.notna().all().all(), "quedaron NaN sin imputar"
    assert np.isfinite(X.to_numpy()).all()


def test_ninguna_caracteristica_sola_resuelve_el_problema(panel, cals):
    """
    GUARDIA CONTRA FUGAS. Si una sola característica se lleva casi toda la
    importancia, lo más probable es que el generador la esté regalando. Así se
    encontró que la intensidad exportadora de las limpias y la de las
    subfacturadoras venían de rangos disjuntos.
    """
    imp = det.importancia(panel, cals, repeticiones=3)
    positivas = imp[imp > 0]
    if len(positivas) < 2:
        pytest.skip("importancia degenerada en esta semilla")
    assert positivas.iloc[0] / positivas.sum() < 0.95, (
        f"«{positivas.index[0]}» explica el {positivas.iloc[0] / positivas.sum():.0%} "
        "de la señal: revisá el generador antes de festejar")


# ---------------------------------------------------------------------------
# Las métricas
# ---------------------------------------------------------------------------
def test_el_detector_le_gana_al_azar(resultado):
    assert resultado["pr_auc"] > 5 * resultado["azar"]
    assert resultado["precision_en_k"] > resultado["azar"]


def test_el_azar_de_pr_auc_es_la_prevalencia_y_no_un_medio(resultado):
    """
    Bajo desbalance extremo el piso de PR-AUC es la prevalencia. Compararlo contra
    0,5 —el piso de ROC-AUC— haría parecer malo a un detector que anda bien.
    """
    assert resultado["azar"] == pytest.approx(
        resultado["positivas"] / resultado["firmas"], rel=1e-9)


def test_el_roc_auc_exagera_frente_al_pr_auc(resultado):
    """
    Se informa porque todo el mundo lo pide, con la advertencia puesta: se apoya en
    la tasa de falsos positivos y con 96% de negativos esa tasa se mueve poco aunque
    las alertas sean mayoritariamente falsas.
    """
    assert resultado["roc_auc"] > resultado["pr_auc"]


def test_el_presupuesto_de_alertas_se_respeta(panel, cals):
    r = det.evaluar(panel, cals, presupuesto=50)
    assert r["presupuesto"] == 50
    assert 0.0 <= r["precision_en_k"] <= 1.0


def test_un_presupuesto_mas_chico_no_baja_la_precision(panel, cals):
    """Alertar menos y mejor es el comportamiento esperado de un ranking que ordena."""
    chico = det.evaluar(panel, cals, presupuesto=30)["precision_en_k"]
    grande = det.evaluar(panel, cals, presupuesto=300)["precision_en_k"]
    assert chico >= grande


def test_con_muy_pocas_positivas_falla_en_vez_de_estimar(cals):
    d = fs.generar(n_firmas=200, ejercicios=2, semilla=3, prevalencia=0.01)
    with pytest.raises(ValueError, match="pocas firmas"):
        det.evaluar(d, cals)


def test_es_determinista_a_igual_semilla(panel, cals):
    a = det.evaluar(panel, cals, semilla=4)
    b = det.evaluar(panel, cals, semilla=4)
    assert a["pr_auc"] == b["pr_auc"] and a["precision_en_k"] == b["precision_en_k"]


# ---------------------------------------------------------------------------
# Qué maniobra se ve y cuál no
# ---------------------------------------------------------------------------
def test_reporta_recall_de_cada_tipologia_presente(panel, resultado):
    presentes = set(panel.loc[panel["tipologia"] != "limpia", "tipologia"])
    assert set(resultado["recall_por_tipologia"]) == presentes


def test_un_panel_de_solo_pantallas_es_trivial(cals, monkeypatch):
    """
    LA RAZÓN DE HABER AGREGADO LA FACHADA. Con sólo empresas pantalla el problema se
    resuelve perfecto, y cualquier detector evaluado ahí queda sobreestimado: la
    pantalla no tiene cuerpo y se ve sola.
    """
    monkeypatch.setattr(fs, "TIPOLOGIAS",
                        {k: v for k, v in fs.TIPOLOGIAS.items()
                         if k in ("limpia", "pantalla")})
    d = fs.generar(n_firmas=2500, ejercicios=4, semilla=21, prevalencia=0.04)
    assert det.evaluar(d, cals)["pr_auc"] > 0.95


def test_la_sobrefacturacion_es_la_mas_dificil(cals, monkeypatch):
    """
    RESULTADO, NO BUG. Aislada, la sobrefacturación apenas supera al azar: su señal
    en el margen es de ~0,06 desvíos de la dispersión natural de rentabilidad entre
    empresas, y su intensidad importadora la comparte con los importadores legítimos.
    En un panel con todas las tipologías y presupuesto acotado, el detector gasta las
    alertas en las que sí se ven y nunca llega a estas.
    """
    # El original se captura UNA vez: filtrar sobre el valor ya parcheado dejaría
    # cero tipologías sospechosas en la segunda llamada.
    todas = dict(fs.TIPOLOGIAS)

    def solo(nombre):
        monkeypatch.setattr(fs, "TIPOLOGIAS",
                            {k: v for k, v in todas.items()
                             if k in ("limpia", nombre)})
        d = fs.generar(n_firmas=2500, ejercicios=4, semilla=21, prevalencia=0.04)
        return det.evaluar(d, cals)["pr_auc"]

    sobre = solo("sobrefacturacion_importaciones")
    pantalla = solo("pantalla")
    assert sobre < 0.40, f"la sobrefacturación no debería verse tan bien: {sobre:.3f}"
    assert sobre < pantalla / 2


def test_la_senal_de_la_sobrefacturacion_esta_enterrada_en_la_dispersion(cals):
    """
    El número que explica el recall cero: la diferencia de margen contra las limpias
    es una fracción del desvío que la rentabilidad tiene entre empresas de por sí.
    Un margen comprimido lo comparte con cualquier empresa que simplemente gana poco.
    """
    d = fs.generar(n_firmas=4000, ejercicios=4, semilla=21, prevalencia=0.30)
    margen_sector = d["sector"].map(lambda s: cals[s].margen_operativo)
    rel = (d["resultado_operativo"] / d["ingresos"]) / margen_sector
    limpias = rel[~d["maniobra_activa"]]
    sobre = rel[(d["tipologia"] == "sobrefacturacion_importaciones") & d["maniobra_activa"]]
    separacion = abs(limpias.mean() - sobre.mean()) / limpias.std()
    assert separacion < 0.25, f"separación de {separacion:.2f} desvíos: revisá el modelado"
