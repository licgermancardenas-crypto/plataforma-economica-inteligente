"""Tests de platec.narrador — dossier, verificación numérica, caché y reintentos.

Ningún test toca la red ni requiere credenciales: el cliente del proveedor se inyecta
como doble. Lo que se prueba de verdad es el VERIFICADOR, que es la pieza que hace
admisible un LLM en una herramienta de análisis; sus casos están escritos contra los
modos de falla reales de un modelo (inventar un número, reescalarlo, derivarlo).
"""
import pandas as pd
import pytest

from platec import data, narrador as nar


# ---------------------------------------------------------------------------
# Dobles del cliente (no hay red en los tests)
# ---------------------------------------------------------------------------
class _Bloque:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Respuesta:
    def __init__(self, texto, stop_reason="end_turn"):
        self.content = [_Bloque(texto)]
        self.stop_reason = stop_reason


class ClienteFalso:
    """Devuelve respuestas de una cola y registra cuántas veces lo llamaron."""

    def __init__(self, respuestas, stop_reason="end_turn"):
        self._cola = list(respuestas)
        self._stop = stop_reason
        self.llamadas = 0
        self.mensajes_recibidos = []
        self.beta = self                        # `cliente.beta.messages` cae acá también
        self.messages = self

    def create(self, **kw):
        self.llamadas += 1
        self.mensajes_recibidos.append(kw["messages"])
        return _Respuesta(self._cola.pop(0), self._stop)


def _dossier(*valores, caveats=()):
    hechos = tuple(nar.Hecho(f"hecho {i}", v, "", 1) for i, v in enumerate(valores))
    return nar.Dossier(titulo="T", contexto="C", hechos=hechos, caveats=tuple(caveats))


@pytest.fixture(autouse=True)
def cache_aislado(tmp_path, monkeypatch):
    """Ningún test debe escribir en data/narrador ni leer lecturas de corridas previas."""
    monkeypatch.setattr(nar, "CACHE_DIR", tmp_path / "narrador")


# ---------------------------------------------------------------------------
# Formato y parseo de números en castellano
# ---------------------------------------------------------------------------
def test_formato_es_ar():
    assert nar._fmt(45511.0, 1) == "45.511,0"
    assert nar._fmt(-0.5, 2) == "-0,50"
    assert nar._fmt(100, 0) == "100"


@pytest.mark.parametrize("texto, esperados", [
    ("subió 2,1% en el mes", [2.1]),
    ("las reservas llegaron a 45.511,0 millones", [45511.0]),
    ("cayó -0,80 pp", [-0.80]),
    ("el índice es 12.076,4 y hay 116 datos", [12076.4, 116.0]),
])
def test_parseo_de_numeros(texto, esperados):
    assert [v for _, v, _ in nar.numeros_en(texto)] == esperados


def test_el_punto_final_de_una_oracion_no_es_separador_de_miles():
    """"...subió 12." no debe leerse como 12 seguido de un grupo de miles."""
    assert [v for _, v, _ in nar.numeros_en("La serie subió 12. Después bajó.")] == [12.0]


# ---------------------------------------------------------------------------
# Verificación: el núcleo del módulo
# ---------------------------------------------------------------------------
def test_verifica_numero_exacto_del_dossier():
    assert nar.verificar("La serie está en 45.511,0 unidades.", _dossier(45511.0)) == []


def test_verifica_redondeo_a_menos_decimales():
    """El modelo puede redondear: 2,14 escrito como 2,1 sigue estando respaldado."""
    assert nar.verificar("subió 2,1%", _dossier(2.14)) == []


def test_detecta_numero_inventado():
    assert nar.verificar("subió 7,3%", _dossier(2.1, 33.8)) == ["7,3"]


def test_detecta_reescalado():
    """Pasar 45.511 millones a '45,5 mil millones' es una cuenta, y las cuentas no son del modelo."""
    assert nar.verificar("las reservas rondan los 45,5 mil millones", _dossier(45511.0)) == ["45,5"]


def test_detecta_valor_derivado():
    """Restar dos hechos para obtener un tercero también es calcular."""
    assert nar.verificar("la diferencia es de 31,7 puntos", _dossier(33.8, 2.1)) == ["31,7"]


def test_los_anios_no_se_marcan():
    assert nar.verificar("desde 2016 hasta 2026 la serie subió 2,1%", _dossier(2.1)) == []


def test_un_numero_con_separador_de_miles_no_pasa_por_ano():
    """El riesgo país en pb vive en el rango de los años: "2.052 pb" no es 2052 d.C."""
    assert nar.verificar("el riesgo país promedió 2.052 pb", _dossier(1011.4)) == ["2.052"]


def test_el_riesgo_pais_legitimo_en_ese_rango_se_sigue_verificando():
    assert nar.verificar("el riesgo país promedió 2.052 pb", _dossier(2052.0)) == []


def test_un_ano_con_decimales_no_es_un_ano():
    """2016,0 no es un año: es una magnitud, y como tal necesita respaldo."""
    assert nar.verificar("el nivel llegó a 2016,0", _dossier(2.1)) == ["2016,0"]


def test_no_repite_el_mismo_huerfano():
    assert nar.verificar("7,3% y otra vez 7,3%", _dossier(1.0)) == ["7,3"]


# ---------------------------------------------------------------------------
# Hash del dossier: la base del determinismo
# ---------------------------------------------------------------------------
def test_mismo_dossier_mismo_hash():
    assert _dossier(1.0, 2.0).hash() == _dossier(1.0, 2.0).hash()


def test_distintos_datos_distinto_hash():
    assert _dossier(1.0).hash() != _dossier(2.0).hash()


def test_cambiar_la_version_del_prompt_invalida_el_hash(monkeypatch):
    """Reglas de redacción nuevas => las lecturas viejas ya no valen."""
    antes = _dossier(1.0).hash()
    monkeypatch.setattr(nar, "PROMPT_VERSION", "999")
    assert _dossier(1.0).hash() != antes


def test_los_caveats_entran_al_hash():
    a = _dossier(1.0)
    b = _dossier(1.0, caveats=("ojo con esto",))
    assert a.hash() != b.hash()


# ---------------------------------------------------------------------------
# Redacción: reintentos y verificación
# ---------------------------------------------------------------------------
def test_redaccion_limpia_al_primer_intento():
    cli = ClienteFalso(["La serie subió 2,1% en el mes."])
    lec = nar.redactar(_dossier(2.1), cliente=cli, usar_cache=False)
    assert lec.verificado and lec.intentos == 1 and cli.llamadas == 1
    assert lec.numeros_huerfanos == ()


def test_reintenta_cuando_inventa_un_numero():
    cli = ClienteFalso(["subió 7,3%", "subió 2,1%"])
    lec = nar.redactar(_dossier(2.1), cliente=cli, usar_cache=False)
    assert lec.verificado and lec.intentos == 2 and cli.llamadas == 2
    # el reintento tiene que decirle CUÁL número está de más, no un reproche genérico
    assert "7,3" in cli.mensajes_recibidos[1][-1]["content"]


def test_agotados_los_reintentos_devuelve_marcado_no_verificado():
    """Se devuelve igual, señalizado: tapar el problema sería peor que exhibirlo."""
    cli = ClienteFalso(["subió 7,3%", "subió 9,9%"])
    lec = nar.redactar(_dossier(2.1), cliente=cli, usar_cache=False)
    assert not lec.verificado
    assert lec.numeros_huerfanos == ("9,9",)
    assert lec.texto == "subió 9,9%"


def test_una_respuesta_truncada_es_un_error_y_no_una_lectura():
    cli = ClienteFalso(["texto a medio "], stop_reason="max_tokens")
    with pytest.raises(RuntimeError, match="truncó"):
        nar.redactar(_dossier(2.1), cliente=cli, usar_cache=False, reintentos=0)


def test_una_negativa_del_modelo_no_se_confunde_con_una_lectura():
    cli = ClienteFalso([""], stop_reason="refusal")
    with pytest.raises(RuntimeError, match="declinó"):
        nar.redactar(_dossier(2.1), cliente=cli, usar_cache=False, reintentos=0)


# ---------------------------------------------------------------------------
# Caché: mismos datos, mismo texto
# ---------------------------------------------------------------------------
def test_la_segunda_lectura_sale_del_cache_sin_llamar_al_modelo():
    d = _dossier(2.1)
    cli = ClienteFalso(["subió 2,1%"])
    primera = nar.redactar(d, cliente=cli)
    segunda = nar.redactar(d, cliente=cli)
    assert cli.llamadas == 1                     # la segunda no gastó una llamada
    assert segunda.texto == primera.texto
    assert segunda.desde_cache and not primera.desde_cache


def test_datos_nuevos_no_reusan_la_lectura_vieja():
    cli = ClienteFalso(["subió 2,1%", "subió 3,4%"])
    nar.redactar(_dossier(2.1), cliente=cli)
    lec = nar.redactar(_dossier(3.4), cliente=cli)
    assert cli.llamadas == 2 and lec.texto == "subió 3,4%"


def test_el_estado_de_verificacion_sobrevive_al_cache():
    d = _dossier(2.1)
    nar.redactar(d, cliente=ClienteFalso(["subió 7,3%", "subió 9,9%"]))
    lec = nar.redactar(d, cliente=ClienteFalso([]))
    assert lec.desde_cache and not lec.verificado and lec.numeros_huerfanos == ("9,9",)


def test_un_cache_corrupto_se_regenera_en_vez_de_romper(tmp_path):
    d = _dossier(2.1)
    nar.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (nar.CACHE_DIR / f"{d.hash()}.json").write_text("{ esto no es json", encoding="utf-8")
    lec = nar.redactar(d, cliente=ClienteFalso(["subió 2,1%"]))
    assert lec.texto == "subió 2,1%"


def test_forzar_reescribe_la_lectura_en_vez_de_devolver_la_cacheada():
    """El "rehacer" de la UI: mismos datos, texto nuevo, y el nuevo queda cacheado."""
    d = _dossier(2.1)
    cli = ClienteFalso(["subió 2,1%", "avanzó 2,1%"])
    nar.redactar(d, cliente=cli)
    rehecha = nar.redactar(d, cliente=cli, forzar=True)
    assert rehecha.texto == "avanzó 2,1%" and cli.llamadas == 2
    assert nar.cacheada(d).texto == "avanzó 2,1%"


def test_limpiar_cache_cuenta_lo_que_borra():
    nar.redactar(_dossier(2.1), cliente=ClienteFalso(["subió 2,1%"]))
    nar.redactar(_dossier(3.4), cliente=ClienteFalso(["subió 3,4%"]))
    assert nar.limpiar_cache() == 2
    assert nar.limpiar_cache() == 0


# ---------------------------------------------------------------------------
# Disponibilidad: sin credenciales el módulo se aparta, no explota
# ---------------------------------------------------------------------------
def test_sin_credenciales_no_esta_disponible(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert nar.disponible() is False


def test_sin_credenciales_redactar_explica_la_alternativa(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        nar.redactar(_dossier(2.1), usar_cache=False)


# ---------------------------------------------------------------------------
# Construcción de dossiers contra la base real
# ---------------------------------------------------------------------------
requiere_db = pytest.mark.skipif(
    not data.DB_PATH.exists(), reason="requiere data/plataforma.db (correr init_db + ingest)"
)


@requiere_db
def test_dossier_de_serie_trae_hechos_y_caveats():
    d = nar.dossier_serie("ipc_general")
    etiquetas = [h.etiqueta for h in d.hechos]
    assert "Último valor" in etiquetas
    assert any("Percentil" in e for e in etiquetas)
    # el hueco del INDEC intervenido tiene que viajar con el dato, no quedar implícito
    assert any("INTERVENIDO" in c for c in d.caveats)


@requiere_db
def test_el_dossier_de_una_tasa_mide_los_cambios_en_pp():
    """Que el desempleo pase de 7,0 a 7,3 es +0,3 pp, no '+4,3%'."""
    d = nar.dossier_serie("desempleo")
    cambios = [h for h in d.hechos if "ambio" in h.etiqueta or "ariación" in h.etiqueta]
    assert cambios and all(h.unidad == "pp" for h in cambios)


@requiere_db
def test_todo_numero_del_dossier_se_verifica_contra_si_mismo():
    """Coherencia interna: el texto del dossier no puede contener números que él mismo rechace."""
    d = nar.dossier_serie("reservas")
    for h in d.hechos:
        assert nar.verificar(h.formateado(), d) == [], f"{h.etiqueta} no se verifica"


@requiere_db
def test_dossier_de_gobiernos_declara_los_mandatos_sin_cobertura():
    from platec import gobiernos as gob
    s = gob._serie_transformada("base_monetaria", "pct_pib_stock")
    d = nar.dossier_gobierno("Base monetaria (% PBI)", gob.por_gobierno(s, como="fin"),
                             "% del PBI", "fin")
    # Menem II y De la Rúa son anteriores al PIB trimestral del INDEC (2004)
    assert any("Sin dato suficiente" in c for c in d.caveats)
    assert any("Menem II" in c for c in d.caveats)


@requiere_db
def test_dossier_de_gobiernos_avisa_que_el_mandato_en_curso_esta_incompleto():
    from platec import gobiernos as gob
    s = gob._serie_transformada("reservas", None)
    d = nar.dossier_gobierno("Reservas", gob.por_gobierno(s, como="fin"), "millones USD", "fin")
    assert any("en curso" in c for c in d.caveats)


def test_dossier_de_gobiernos_rechaza_una_metrica_sin_ningun_dato():
    """Todos los mandatos en NaN no es una comparación con huecos: no es una comparación."""
    vacio = pd.DataFrame({"valor": [float("nan"), float("nan")],
                          "en_curso": [False, True]}, index=["A", "B"])
    with pytest.raises(ValueError, match="cobertura"):
        nar.dossier_gobierno("Nada", vacio)
