"""
platec.narrador — redacción de lecturas económicas con LLM, con verificación numérica.
======================================================================================
Etapa 8. El módulo `insights` ya extrae los hechos cuantitativos de una serie; acá se
los REDACTA. La división no es estética: es la que hace que un LLM sea admisible en una
herramienta cuyo valor es el rigor.

EL LLM NO CALCULA. Recibe un `Dossier`: un conjunto cerrado de hechos ya computados por
`platec`, con sus unidades y sus caveats. Su única tarea es escribir prosa sobre eso.

Tres defensas, en orden de importancia:

1. **Verificación numérica post-hoc.** Se extraen todos los números del texto generado y
   se contrastan contra los valores del dossier (`verificar`). Un número que no esté
   respaldado dispara un reintento señalándolo; si el modelo insiste, la lectura se
   devuelve con `verificado=False` y la lista de números huérfanos, para que la UI la
   muestre marcada en vez de servirla como si fuera un dato. La verificación es
   deliberadamente ESTRICTA: reescalar (pasar 45.511 millones a "45,5 mil millones") es
   una cuenta, y las cuentas son del lado de Python.

2. **Determinismo por caché.** Una herramienta de análisis que devuelve un texto distinto
   cada vez que se la abre no es reproducible. El determinismo NO se consigue bajando la
   temperatura: los modelos actuales de la familia Opus rechazan `temperature` con un 400.
   Se consigue cacheando por hash del dossier + versión del prompt: mismos datos, mismo
   texto, hasta que los datos cambien.

3. **Degradación limpia.** Sin credenciales el módulo no explota: `disponible()` devuelve
   False y el dashboard sigue mostrando el panel de insights determinístico de siempre.
   La capa de IA es un agregado, nunca un requisito para ver el tablero.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import data, insights, stats

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
MODELO = "claude-opus-5"

# Versión del prompt. Entra en el hash del caché: al tocar las reglas de redacción
# hay que invalidar las lecturas viejas, porque fueron escritas con otras reglas.
PROMPT_VERSION = "2"

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "narrador"

# Techo de tokens. La salida son 3-5 oraciones, pero el pensamiento adaptativo también
# consume del mismo presupuesto, así que el margen es para él, no para la prosa.
MAX_TOKENS = 8000

SISTEMA = """\
Sos un economista argentino especializado en econometría aplicada. Escribís la lectura \
de indicadores macro para una plataforma de análisis propia: el lector es vos mismo \
dentro de seis meses, no un público general.

REGLAS DURAS

1. NO CALCULÁS. Todos los números ya vienen calculados en el dossier. Usá exactamente los \
valores y las unidades que figuran ahí: no los reescales (nada de pasar "45.511 millones" \
a "45,5 mil millones"), no los conviertas de moneda, no los promedies, no restes uno de \
otro para obtener un tercero. Si un valor viene con signo negativo, escribilo CON su signo \
(−0,80 pp), no lo pases a positivo describiendo la dirección en palabras.

2. NO USES NINGÚN NÚMERO QUE NO ESTÉ EN EL DOSSIER. Los años son la única excepción. Si te \
falta un dato para afirmar algo, no lo afirmes: decí que no está disponible.

3. CAUSALIDAD. Afirmá una relación causal solo si el dossier la declara explícitamente. Un \
movimiento conjunto es una correlación y se escribe como tal. No expliques POR QUÉ pasó \
algo si el dossier no trae la evidencia: describí qué pasó.

4. LOS CAVEATS NO SON DECORATIVOS. Si el dossier trae una advertencia que afecta la lectura \
(un tramo de datos excluido por intervención, un intervalo de confianza ancho, un supuesto \
de identificación, un dato provisorio), incorporala a la prosa. No la relegues a una \
oración final de descargo.

5. TONO. Español rioplatense, técnico y seco. Sin adjetivos de color ("preocupante", \
"alentador", "dramático"), sin recomendaciones de política, sin pronósticos. Describís el \
estado de una serie, no opinás sobre el gobierno.

6. EXTENSIÓN. Entre 3 y 5 oraciones. Prosa corrida, sin títulos, sin viñetas, sin markdown. \
Empezá por lo que un analista miraría primero, no por el nombre de la serie.
"""


# ---------------------------------------------------------------------------
# Dossier: el conjunto cerrado de hechos que el modelo puede usar
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Hecho:
    """Un número calculado por platec, con su etiqueta y su unidad."""
    etiqueta: str
    valor: float
    unidad: str = ""
    decimales: int = 1

    def formateado(self) -> str:
        return f"{_fmt(self.valor, self.decimales)}{' ' + self.unidad if self.unidad else ''}"


@dataclass(frozen=True)
class Dossier:
    """
    Todo lo que el modelo tiene permitido saber. Cerrado a propósito: lo que no está
    acá no puede aparecer en el texto sin que la verificación lo marque.
    """
    titulo: str
    contexto: str
    hechos: tuple[Hecho, ...] = ()
    caveats: tuple[str, ...] = ()
    pregunta: str = "Escribí la lectura de esta serie."

    def valores(self) -> list[float]:
        return [h.valor for h in self.hechos]

    def a_texto(self) -> str:
        """El bloque que se le pasa al modelo. Determinístico: sin timestamps ni orden variable."""
        lineas = [f"# {self.titulo}", "", self.contexto, "", "## Hechos"]
        lineas += [f"- {h.etiqueta}: {h.formateado()}" for h in self.hechos]
        if self.caveats:
            lineas += ["", "## Advertencias sobre estos datos"]
            lineas += [f"- {c}" for c in self.caveats]
        return "\n".join(lineas)

    def hash(self) -> str:
        crudo = f"{PROMPT_VERSION}\x00{MODELO}\x00{self.a_texto()}\x00{self.pregunta}"
        return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Lectura:
    """Resultado de una redacción, con su procedencia y su estado de verificación."""
    texto: str
    verificado: bool = True
    numeros_huerfanos: tuple[str, ...] = ()
    desde_cache: bool = False
    modelo: str = MODELO
    intentos: int = 1


# ---------------------------------------------------------------------------
# Formato y parseo de números en castellano
# ---------------------------------------------------------------------------
def _fmt(v: float, decimales: int = 1) -> str:
    """Formato es-AR: separador de miles '.', decimal ','."""
    s = f"{v:,.{decimales}f}"                      # 45,511.0
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# Un número en castellano: miles con '.' en grupos de exactamente 3, decimal con ','.
# Exigir los grupos de 3 evita comerse el punto final de una oración ("... subió 12.").
_RE_NUMERO = re.compile(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?")

# El modelo escribe con tipografía correcta, y el menos tipográfico (U+2212) NO es el
# guion ASCII. Sin normalizarlo, "−0,80" se lee como +0,80 y una IRF negativa legítima
# se marca como huérfana: un falso positivo garantizado en todo dossier con caídas.
# Se normaliza SOLO el menos matemático. La raya (–, U+2013) queda afuera a propósito:
# separa rangos ("2017–2026") y convertirla en signo inventaría un "-2026".
_MENOS_UNICODE = "\u2212"


def numeros_en(texto: str) -> list[tuple[str, float, int]]:
    """
    Todos los números del texto como (crudo, valor, decimales_escritos).
    `decimales_escritos` es lo que permite comparar con la misma precisión con la que
    el modelo escribió: si redondeó a un decimal, se lo compara redondeado a un decimal.
    """
    out: list[tuple[str, float, int]] = []
    for m in _RE_NUMERO.finditer(texto.replace(_MENOS_UNICODE, "-")):
        crudo = m.group(0)
        limpio = crudo.replace(".", "").replace(",", ".")
        try:
            valor = float(limpio)
        except ValueError:                          # pragma: no cover - el regex ya lo garantiza
            continue
        dec = len(crudo.split(",")[1]) if "," in crudo else 0
        out.append((crudo, valor, dec))
    return out


def _es_anio(crudo: str, valor: float, decimales: int) -> bool:
    """
    Los años son la única categoría de número que el modelo puede escribir de memoria.

    Se exige que venga SIN separador de miles, y no solo que caiga en el rango: el riesgo
    país en puntos básicos vive en 700-7000, así que un valor inventado como "2.052 pb" se
    haría pasar por año y saldría sin marcar. Un año no se escribe nunca "2.052".
    """
    return ("." not in crudo and decimales == 0
            and float(valor).is_integer() and 1900 <= valor <= 2100)


def verificar(texto: str, dossier: Dossier) -> list[str]:
    """
    Números del texto que NO están respaldados por el dossier, en orden de aparición.

    El criterio es el redondeo: un número escrito con `d` decimales está respaldado si
    algún valor del dossier redondeado a `d` decimales coincide. Nada de tolerancias
    relativas ni de reescalados — un reescalado es una cuenta, y las cuentas no son del
    modelo. Lista vacía = todo verificado.
    """
    permitidos = dossier.valores()
    huerfanos: list[str] = []
    for crudo, valor, dec in numeros_en(texto):
        if _es_anio(crudo, valor, dec):
            continue
        if any(round(p, dec) == valor for p in permitidos):
            continue
        if crudo not in huerfanos:
            huerfanos.append(crudo)
    return huerfanos


# ---------------------------------------------------------------------------
# Constructores de dossier (puros: no tocan la red)
# ---------------------------------------------------------------------------
_PERIODOS_ANUALES = {"D": 252, "M": 12, "Q": 4}
_NOMBRE_PERIODO = {"D": "diaria", "M": "mensual", "Q": "trimestral"}


def dossier_serie(sid: str) -> Dossier:
    """Dossier de una serie del catálogo: nivel, variaciones, posición y dinámica."""
    s = data.get_series(sid)
    if s.dropna().empty:
        raise ValueError(f"la serie {sid} no tiene observaciones utilizables")
    meta = s.attrs
    s = s.dropna()
    freq = meta.get("frequency", "M")
    es_tasa = meta.get("kind") == "rate"
    unidad = meta.get("unit", "")
    n_anual = _PERIODOS_ANUALES.get(freq, 12)

    ultimo = float(s.iloc[-1])
    hechos = [
        Hecho("Último valor", ultimo, unidad, 2 if abs(ultimo) < 100 else 1),
        Hecho("Observaciones disponibles", float(len(s)), "datos", 0),
    ]

    # Variaciones. En una tasa el cambio se mide en puntos porcentuales, no en % del %:
    # que el desempleo pase de 7% a 7,3% es +0,3 pp, no "subió 4,3%".
    if len(s) >= 2:
        if es_tasa:
            hechos.append(Hecho("Cambio respecto del período anterior",
                                ultimo - float(s.iloc[-2]), "pp", 2))
        else:
            hechos.append(Hecho("Variación respecto del período anterior",
                                float(stats.variacion(s).iloc[-1]), "%", 1))
    if len(s) > n_anual:
        previo = float(s.iloc[-1 - n_anual])
        if es_tasa:
            hechos.append(Hecho("Cambio interanual", ultimo - previo, "pp", 2))
        elif previo != 0:
            hechos.append(Hecho("Variación interanual", (ultimo / previo - 1) * 100, "%", 1))

    hechos.append(Hecho("Percentil dentro de su historia completa",
                        insights.posicion_historica(s), "", 0))
    r = insights.racha(s)
    if abs(r) >= 2:
        hechos.append(Hecho(f"Períodos consecutivos {'en alza' if r > 0 else 'a la baja'}",
                            float(abs(r)), "períodos", 0))
    m = insights.momentum(s)
    if pd.notna(m):
        hechos.append(Hecho("Momentum: nivel reciente vs. su promedio de mediano plazo",
                            float(m), "%", 1))

    caveats: list[str] = []
    if insights.es_anomalia(s):
        caveats.append("El último dato es atípico frente al comportamiento reciente de la "
                       "serie (z-score móvil por encima del umbral). Puede ser un quiebre "
                       "real o un dato provisorio: no conviene leerlo como tendencia.")
    if sid.startswith("ipc") or meta.get("indicator_id") == "inflacion":
        caveats.append("El tramo 2007-2015 del IPC oficial está marcado INTERVENIDO y "
                       "excluido de esta serie: donde aparezca un hueco, es eso.")
    ultima_fecha = s.index[-1].date().isoformat()
    caveats.append(f"El último dato disponible es del {ultima_fecha}; toda la lectura está "
                   f"referida a esa fecha, no a hoy.")

    contexto = (
        f"Serie «{meta.get('name', sid)}» ({meta.get('source_id', 'fuente no declarada')}), "
        f"frecuencia {_NOMBRE_PERIODO.get(freq, freq)}, medida en {unidad or 'unidades sin declarar'}. "
        f"Cubre desde {s.index[0].date().isoformat()} hasta {ultima_fecha}. "
        f"{'Es una tasa: sus cambios se expresan en puntos porcentuales (pp).' if es_tasa else ''}"
    ).strip()

    return Dossier(titulo=f"Lectura de {meta.get('name', sid)}",
                   contexto=contexto, hechos=tuple(hechos), caveats=tuple(caveats))


def dossier_gobierno(etiqueta: str, resumen: pd.DataFrame,
                    unidad: str = "", como: str = "promedio") -> Dossier:
    """
    Dossier de una métrica comparada entre mandatos, a partir del resumen YA calculado
    por `gobiernos.por_gobierno`.

    Recibe el resumen en vez del nombre de la métrica a propósito: así el dossier
    describe exactamente los números que el usuario tiene en pantalla, en vez de
    recalcularlos por su cuenta y arriesgarse a redactar sobre otra cosa.
    """
    con_dato = resumen["valor"].dropna()
    if con_dato.empty:
        raise ValueError(f"«{etiqueta}» no tiene ningún mandato con cobertura suficiente")

    decimales = 0 if con_dato.abs().max() >= 1000 else 1
    hechos = [Hecho(str(g), float(v), unidad, decimales) for g, v in con_dato.items()]

    faltantes = [str(g) for g in resumen.index if pd.isna(resumen.loc[g, "valor"])]
    en_curso = [str(g) for g in resumen.index
                if bool(resumen.loc[g, "en_curso"]) and g in con_dato.index]

    caveats = [
        "Las magnitudes en pesos vienen normalizadas por PIB nominal o expresadas en "
        "dólares. No son comparables contra valores nominales de otras fuentes.",
        "Cada mandato dura distinto y arranca en un punto distinto del ciclo. La "
        "comparación de niveles describe qué pasó durante cada período; no atribuye "
        "el resultado a la gestión.",
    ]
    if faltantes:
        caveats.append(
            "Sin dato suficiente (la serie no cubre el 60% del mandato) en: "
            + ", ".join(faltantes)
            + ". Es ausencia de datos, no un cero ni un mal desempeño: no los compares.")
    if en_curso:
        caveats.append(
            f"Mandato en curso, con el período incompleto: {', '.join(en_curso)}. "
            "Su valor no es comparable de igual a igual con los mandatos cerrados.")

    _COMO = {"promedio": "el promedio del mandato", "fin": "el valor al cierre del mandato",
             "inicio": "el valor al inicio del mandato",
             "cambio": "el cambio entre el inicio y el cierre del mandato",
             "var_anual": "la variación anualizada punta a punta",
             "acumulado": "el acumulado del mandato", "maximo": "el máximo del mandato",
             "minimo": "el mínimo del mandato"}
    contexto = (f"Métrica «{etiqueta}» comparada entre mandatos presidenciales argentinos. "
                f"Cada valor es {_COMO.get(como, como)}"
                f"{', medido en ' + unidad if unidad else ''}.")

    return Dossier(titulo=f"Comparación entre gobiernos: {etiqueta}",
                   contexto=contexto, hechos=tuple(hechos), caveats=tuple(caveats),
                   pregunta="Escribí la lectura comparativa de esta métrica entre mandatos.")


# ---------------------------------------------------------------------------
# Dossiers econométricos
# ---------------------------------------------------------------------------
# Estos constructores NO reestiman nada: reciben los objetos que ya calcularon
# `econometria` y `nowcast`, igual que `dossier_gobierno` recibe el resumen. Por la
# razón de siempre —el dossier tiene que describir exactamente los números que están
# en pantalla, no otros parecidos— y por una segunda que es de arquitectura: reestimar
# un VAR con bootstrap cuesta segundos, y `narrador` se importa en el arranque del
# dashboard. Se tipa por comportamiento y no por clase, así este módulo sigue sin
# arrastrar `statsmodels` ni `scikit-learn`.
#
# LO QUE SE DEJA AFUERA A PROPÓSITO. La tabla de Granger mensual reporta el «p mínimo
# sobre 6 rezagos». Ese mínimo no es un p-valor: es el mejor de seis pruebas, sin
# corregir por comparaciones múltiples, y el propio proyecto lo tiene marcado como
# criterio a migrar (hallazgos_econometricos.md, §Limitaciones). Un número que no
# creemos no entra a un dossier cuya razón de ser es que el modelo no pueda afirmar de
# más: si entrara, el modelo escribiría «causa en sentido de Granger con p = 0,001» y
# la culpa no sería suya. Lo mismo con los coeficientes del ElasticNet: están sin
# estandarizar, así que sus magnitudes no son comparables entre variables de escalas
# distintas y no sostienen la frase «tal variable pesa más» que invitarían a escribir.


def _orden_legible(orden, etiquetas: dict | None = None) -> str:
    """El ordenamiento de Cholesky como cadena, con nombres humanos si los hay."""
    e = etiquetas or {}
    return " → ".join(str(e.get(v, v)) for v in orden)


def dossier_canal(banda, ordenes=None, *, shock: str, respuesta: str,
                  pt=None, etiquetas: dict | None = None,
                  desde: str = "", caveats_extra: tuple[str, ...] = ()) -> Dossier:
    """
    Dossier de un canal de transmisión: la respuesta acumulada de `respuesta` ante un
    shock en `shock`, con su intervalo y su sensibilidad al supuesto de identificación.

    `banda` es un `econometria.IRFBandas`; `ordenes`, el DataFrame de
    `econometria.sensibilidad_orden` (una columna por ordenamiento). `pt` es opcional:
    si viene un `econometria.PassThrough`, se agrega la ruta por rezagos distribuidos
    para el mismo canal.

    El punto de este dossier es que el modelo NO pueda escribir solo la estimación
    puntual. Los límites del intervalo, su amplitud, en cuántos horizontes excluye al
    cero y la misma respuesta bajo ordenamientos alternativos entran como hechos de
    primera clase: son la única forma de que la prosa pueda decir cuánto de la
    conclusión es evidencia y cuánto es supuesto.
    """
    h = banda.puntual.index[-1]
    lo, hi = float(banda.inferior[h]), float(banda.superior[h])
    signif = list(banda.significativa_en)

    hechos = [
        Hecho(f"Respuesta acumulada de {respuesta} a un shock de {shock}, "
              f"estimación puntual", float(banda.puntual[h]), "pp", 2),
        Hecho("Límite inferior del intervalo", lo, "pp", 2),
        Hecho("Límite superior del intervalo", hi, "pp", 2),
        # La amplitud entra ya calculada: restar los dos límites es una cuenta, y una
        # cuenta hecha por el modelo se marca como huérfana aunque el resultado sea
        # correcto. Sin este hecho la prosa no puede hablar de cuán ancha es la banda,
        # que es justamente lo que hay que decir de este resultado.
        Hecho("Amplitud del intervalo", hi - lo, "pp", 2),
        Hecho("Confianza del intervalo", (1 - banda.signif) * 100, "%", 0),
        Hecho("Horizonte al que corresponde la respuesta", float(h), "meses", 0),
        Hecho("Horizontes evaluados", float(len(banda.puntual)), "", 0),
        Hecho("Horizontes en los que el intervalo excluye al cero",
              float(len(signif)), "", 0),
        Hecho("Rezagos del VAR (elegidos por AIC)", float(banda.p), "", 0),
        Hecho("Observaciones del VAR", float(banda.n), "", 0),
        Hecho("Réplicas del bootstrap", float(banda.repl), "", 0),
    ]

    orden_base = _orden_legible(banda.orden, etiquetas)
    if ordenes is not None and len(ordenes.columns):
        for col in ordenes.columns:
            legible = _orden_legible(str(col).split(" → "), etiquetas)
            hechos.append(Hecho(f"La misma respuesta bajo el ordenamiento {legible}",
                                float(ordenes[col].iloc[-1]), "pp", 2))

    if pt is not None:
        lags = int(pt.acumulado.index[-1])
        hechos += [
            # ×100 en Python y no en la prosa: `acumulado` es una fracción y pasar
            # 0,24 a "24%" es un reescalado, exactamente lo que el verificador marca.
            Hecho(f"Traslado acumulado a {lags} meses por rezagos distribuidos",
                  float(pt.acumulado.iloc[-1]) * 100, "%", 1),
            Hecho("Traslado en el mismo mes del shock (impacto)",
                  float(pt.coef_por_lag.iloc[0]) * 100, "%", 1),
            Hecho("Rezagos de la regresión de rezagos distribuidos", float(lags), "meses", 0),
            Hecho("R² de la regresión de rezagos distribuidos", float(pt.r2), "", 3),
            Hecho("Observaciones de la regresión de rezagos distribuidos",
                  float(pt.n), "", 0),
        ]

    caveats = [
        f"El ordenamiento de Cholesky ({orden_base}) es un supuesto del analista, no algo "
        "que los datos identifiquen: impone qué variable puede afectar a cuál dentro del "
        "mismo mes. Por eso se reporta la misma respuesta bajo ordenamientos alternativos. "
        "Si el signo se sostiene al reordenar, es evidencia; si cambia, es el supuesto.",
        "El intervalo son percentiles de un bootstrap de residuos, sin corrección de "
        "sesgo. En muestras cortas ese intervalo tiende a quedar angosto: es un piso de "
        "la incertidumbre, no un techo.",
        "El shock es de un desvío estándar de la propia serie —una unidad estadística de "
        "esta muestra—, no una devaluación ni un salto de riesgo de una magnitud elegida. "
        "La respuesta está en puntos porcentuales de la variación mensual.",
        "El sistema se estima en log-diferencias mensuales, no en niveles: el IPC resulta "
        "I(2) y el tipo de cambio I(1), órdenes distintos que no admiten una cointegración "
        "estándar. Acá hay dinámica de corto plazo; no hay relación de largo plazo estimada.",
        "La muestra mensual cruza cambios de régimen (2018-19, 2023-24) y el VAR se estima "
        "pooleado sobre todos ellos: no se testeó estabilidad de parámetros. Los "
        "coeficientes son un promedio entre regímenes que pueden no compartir mecanismo.",
    ]
    if h not in signif:
        caveats.append(
            "En el horizonte que se reporta el intervalo contiene al cero: la estimación "
            "puntual no se distingue de cero ahí. No la leas como un efecto establecido.")
    if pt is not None:
        caveats.append(
            "Las dos rutas no son comparables de igual a igual: la regresión de rezagos "
            "distribuidos impone que el tipo de cambio es exógeno y el VAR no. Que la "
            "regresión dé un número más cerrado viene de ese supuesto, no de más "
            "evidencia. Que ambas difieran es esperable y no es un error de estimación.")
    caveats += list(caveats_extra)

    contexto = (
        f"Canal de transmisión {shock} → {respuesta} estimado con un VAR mensual en "
        f"log-diferencias{f', muestra desde {desde}' if desde else ''}. La respuesta es "
        f"ACUMULADA hasta el horizonte indicado, ante un shock de un desvío estándar en "
        f"{shock}, identificado por descomposición de Cholesky.")

    return Dossier(
        titulo=f"Canal {shock} → {respuesta}", contexto=contexto,
        hechos=tuple(hechos), caveats=tuple(caveats),
        pregunta=("Escribí la lectura de este canal de transmisión. Decí qué muestra la "
                  "estimación puntual, cuánta incertidumbre tiene alrededor y si la "
                  "conclusión sobrevive al cambio de ordenamiento."))


def dossier_nowcast(nc, nc_actual: float, infl_ultima: float, ph=None,
                    desde: str = "") -> Dossier:
    """
    Dossier del nowcast de inflación (y, si viene `ph`, de la curva de Phillips).

    `nc` es un `nowcast.ResultadoNowcast`; `nc_actual`, la estimación para el mes en
    curso; `infl_ultima`, el último dato oficial publicado.
    """
    hechos = [
        Hecho("Nowcast de la inflación del mes en curso", float(nc_actual), "%", 2),
        Hecho("Último dato de inflación mensual publicado", float(infl_ultima), "%", 2),
        # Precalculada por lo mismo que la amplitud del intervalo: la diferencia entre
        # dos hechos autorizados sigue siendo una cuenta del lado del modelo.
        Hecho("Diferencia entre el nowcast y el último dato publicado",
              float(nc_actual) - float(infl_ultima), "pp", 2),
        Hecho("Error del modelo fuera de muestra (RMSE)", float(nc.rmse_modelo), "pp", 2),
        Hecho("Error del benchmark ingenuo fuera de muestra (RMSE)",
              float(nc.rmse_naive), "pp", 2),
        Hecho("Reducción del error respecto del benchmark", float(nc.mejora_pct), "%", 1),
        Hecho("Meses evaluados fuera de muestra", float(nc.n_test), "meses", 0),
    ]

    caveats = [
        "El benchmark es un paseo aleatorio: predecir que la inflación del mes será la "
        "del mes pasado. Es el piso que cualquier modelo tiene que superar para ser algo "
        "más que inercia, no un rival exigente.",
        "El RMSE es fuera de muestra con ventana expansiva: cada mes se predice "
        "entrenando solo con datos anteriores. La regularización se reelige una vez por "
        "año de test y se reutiliza los meses siguientes; queda desactualizada, nunca "
        "adelantada: en ningún paso mira datos posteriores al mes que predice.",
        "Es un NOWCAST, no un pronóstico. Usa el tipo de cambio de fin de mes, así que "
        "recién queda disponible al cierre del mes que estima, antes de que publique el "
        "INDEC. No dice nada sobre los meses siguientes.",
        "Los errores están en puntos porcentuales de inflación mensual: hay que leerlos "
        "contra el nivel de inflación del período, no en abstracto.",
    ]

    if ph is not None:
        hechos += [
            Hecho("Pendiente de la curva de Phillips (desempleo → inflación)",
                  float(ph.beta_desempleo), "", 2),
            Hecho("p-valor de esa pendiente", float(ph.p_valor), "", 4),
            Hecho("R² de la curva de Phillips", float(ph.r2), "", 3),
            Hecho("Observaciones de la curva de Phillips", float(ph.n), "", 0),
        ]
        caveats.append(
            "La curva de Phillips se estima con desempleo trimestral, que es la "
            "frecuencia que limita la muestra. Si el p-valor no rechaza, la relación no "
            "está identificada acá y el signo de la pendiente no se debe interpretar: en "
            "Argentina la inflación la gobiernan lo monetario y lo cambiario, no el "
            "mercado de trabajo.")

    contexto = (
        f"Estimación de la inflación mensual del mes en curso con regresión regularizada "
        f"(ElasticNet) sobre variables de alta frecuencia —devaluación oficial y CCL, "
        f"brecha, inercia—, validada con walk-forward contra un benchmark ingenuo"
        f"{f', muestra desde {desde}' if desde else ''}."
        + (" Incluye la curva de Phillips estimada sobre la misma muestra." if ph is not None else ""))

    return Dossier(
        titulo="Nowcast de inflación", contexto=contexto,
        hechos=tuple(hechos), caveats=tuple(caveats),
        pregunta=("Escribí la lectura del nowcast: qué estima para el mes en curso y "
                  "cuánto vale esa estimación a la luz de su error fuera de muestra."))


def dossier_espejo(agregado, contrastes: dict, factor_global_: float,
                   socios_apareados: int) -> Dossier:
    """
    Dossier del comercio espejo: la discrepancia del último año más el contraste
    contra la brecha cambiaria.

    `agregado` es una fila de `comercio_espejo.por_anio` por canal (dict canal →
    dict con gap, gap_pct, cobertura_fob); `contrastes`, el dict canal → resultado
    de `comercio_espejo.contraste_brecha`.
    """
    if not agregado:
        raise ValueError("no hay discrepancia agregada para redactar")

    hechos: list[Hecho] = []
    for canal, fila in agregado.items():
        hechos.append(Hecho(f"Discrepancia del canal {canal} en el último año cerrado",
                            float(fila["gap"]), "millones de dólares", 0))
        hechos.append(Hecho(f"Esa discrepancia como porcentaje del comercio del canal "
                            f"{canal}", float(fila["gap_pct"]), "%", 1))
        hechos.append(Hecho(f"Cobertura de FOB reportado del canal {canal}",
                            float(fila["cobertura_fob"]) * 100, "%", 0))

    for canal, r in contrastes.items():
        hechos.append(Hecho(f"Efecto de la brecha sobre la discrepancia del canal {canal} "
                            f"(por cada punto de brecha)", float(r["beta"]), "pp", 3))
        hechos.append(Hecho(f"Error estándar de ese efecto ({canal})", float(r["se"]), "", 3))
        hechos.append(Hecho(f"p-valor por bootstrap de ese efecto ({canal})",
                            float(r["p_wcb"]), "", 3))
        # Precalculado: multiplicar el coeficiente por cien es una cuenta, y el
        # modelo la haría para expresar el efecto en una brecha de 100%.
        hechos.append(Hecho(f"Discrepancia adicional del canal {canal} al pasar de brecha "
                            f"nula a brecha de 100%", float(r["beta"]) * 100, "pp", 1))
        hechos.append(Hecho(f"Años usados en el contraste ({canal})",
                            float(r["anios"]), "años", 0))

    # El punto de referencia entra como hecho aunque sea una constante elegida por
    # nosotros: la etiqueta de arriba dice "brecha de 100%", así que el modelo va a
    # escribir ese 100 sí o sí. Sin él en el dossier, toda lectura correcta de ese
    # efecto saldría marcada — un falso positivo garantizado, no una defensa.
    hechos.append(Hecho("Brecha de referencia usada para expresar ese efecto",
                        100.0, "%", 0))
    hechos.append(Hecho("Socios comerciales apareados", float(socios_apareados), "", 0))
    hechos.append(Hecho("Factor CIF/FOB global estimado",
                        (factor_global_ - 1) * 100, "%", 1))

    caveats = [
        "Lo medido es una DISCREPANCIA entre lo que declara Argentina y lo que declara "
        "la contraparte, no una estimación de flujos ilícitos. Solo se corrige el flete "
        "(CIF contra FOB); quedan sin corregir las reexportaciones vía terceros países, "
        "los desfases de timing en la aduana y la clasificación distinta de cada lado.",
        "El contraste contra la brecha es una asociación en panel con efectos fijos por "
        "socio, NO una identificación causal. Los años de brecha alta en Argentina son "
        "también años de crisis, controles y recesión, y cualquiera de esas cosas puede "
        "mover la discrepancia por su cuenta.",
        "El p-valor sale de un wild cluster bootstrap sobre quince años. Quince clusters "
        "son pocos: un p entre 0,03 y 0,06 es sugerente, no concluyente.",
        "El factor CIF/FOB se estima por país cuando se puede e imputa cuando no. La "
        "cobertura de FOB reportado dice qué fracción del valor NO depende de esa "
        "imputación; cuanto más baja, más descansa el número en un supuesto.",
        "Comtrade publica con alrededor de un año de rezago y los últimos dos años tienen "
        "menos países reportando que un año cerrado. No los leas como definitivos.",
    ]

    contexto = (
        "Discrepancia del comercio exterior argentino medida contra los registros de las "
        "contrapartes (UN Comtrade), en dos canales: el exportador —subfacturar "
        "exportaciones— y el importador —sobrefacturar importaciones—. En los dos, un "
        "valor positivo indica salida de divisas. Se acompaña del contraste que mide si "
        "esa discrepancia crece con la brecha cambiaria, que es el precio del arbitraje.")

    return Dossier(
        titulo="Comercio espejo y brecha cambiaria", contexto=contexto,
        hechos=tuple(hechos), caveats=tuple(caveats),
        pregunta=("Escribí la lectura del comercio espejo: cuánta discrepancia hay, en qué "
                  "canal, y si responde o no a la brecha cambiaria. Si los dos canales se "
                  "comportan distinto, decilo."))


# ---------------------------------------------------------------------------
# Caché en disco: es lo que hace reproducible la lectura
# ---------------------------------------------------------------------------
def _ruta_cache(h: str) -> Path:
    return CACHE_DIR / f"{h}.json"


def _leer_cache(h: str) -> Lectura | None:
    p = _ruta_cache(h)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None                                  # un caché corrupto se regenera, no rompe
    return Lectura(texto=d["texto"], verificado=d.get("verificado", True),
                   numeros_huerfanos=tuple(d.get("numeros_huerfanos", ())),
                   desde_cache=True, modelo=d.get("modelo", MODELO),
                   intentos=d.get("intentos", 1))


def _escribir_cache(h: str, lec: Lectura) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _ruta_cache(h).write_text(json.dumps({
            "texto": lec.texto, "verificado": lec.verificado,
            "numeros_huerfanos": list(lec.numeros_huerfanos),
            "modelo": lec.modelo, "intentos": lec.intentos,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass                                         # un FS de solo lectura no debe tumbar la app


def cacheada(dossier: Dossier) -> Lectura | None:
    """
    La lectura ya redactada para este dossier, si existe. NO llama al modelo.
    Es lo que permite que el dashboard muestre la lectura al abrir la página sin gastar
    una llamada en cada rerun de Streamlit: si está, se muestra; si no, se ofrece el botón.
    """
    return _leer_cache(dossier.hash())


def limpiar_cache() -> int:
    """Borra las lecturas cacheadas. Devuelve cuántas borró."""
    if not CACHE_DIR.exists():
        return 0
    n = 0
    for p in CACHE_DIR.glob("*.json"):
        p.unlink(); n += 1
    return n


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
def disponible() -> bool:
    """¿Hay SDK y credenciales? Si no, el dashboard usa el panel determinístico."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _cliente():
    import anthropic
    return anthropic.Anthropic()


def _error_de_beta_no_soportada() -> tuple[type[BaseException], ...]:
    """
    El error que hace caer al camino sin beta. Se resuelve tarde y a propósito: sin el SDK
    instalado no hay nada que atrapar, y una tupla vacía en un `except` no atrapa nada —
    que es justo lo que corresponde. Así los tests con cliente inyectado no necesitan el SDK.
    """
    try:
        import anthropic
    except ImportError:
        return ()
    return (anthropic.BadRequestError,)


def _pedir(cliente, mensajes: list[dict]) -> str:
    """
    Una llamada al modelo. `fallbacks` reencamina el pedido si un clasificador de seguridad
    lo declina; si el header beta no está habilitado en la cuenta, se reintenta sin él antes
    de dar el pedido por perdido.
    """
    comun = dict(model=MODELO, max_tokens=MAX_TOKENS, system=SISTEMA,
                 messages=mensajes, output_config={"effort": "medium"})
    try:
        resp = cliente.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **comun)
    except _error_de_beta_no_soportada():
        resp = cliente.messages.create(**comun)

    if resp.stop_reason == "refusal":
        raise RuntimeError("el modelo declinó redactar esta lectura")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(f"la respuesta se truncó en {MAX_TOKENS} tokens")
    texto = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    if not texto:
        raise RuntimeError("el modelo no devolvió texto")
    return texto


def redactar(dossier: Dossier, *, usar_cache: bool = True, forzar: bool = False,
             reintentos: int = 1, cliente=None) -> Lectura:
    """
    Redacta la lectura de un dossier y la verifica contra sus propios números.

    Si el texto trae un número que el dossier no respalda, se reintenta señalándoselo al
    modelo. Agotados los reintentos se devuelve igual, con `verificado=False` y la lista
    de números huérfanos: la decisión de mostrarlo o no es de la UI, no de este módulo —
    tapar el problema sería peor que exhibirlo.

    `forzar` ignora la lectura cacheada pero igual guarda la nueva: es el "rehacer" de
    la UI, para cuando el texto salió pobre con los mismos datos.
    `cliente` se inyecta en los tests para no tocar la red.
    """
    h = dossier.hash()
    if usar_cache and not forzar:
        previa = _leer_cache(h)
        if previa is not None:
            return previa

    if cliente is None:
        if not disponible():
            raise RuntimeError(
                "no hay credenciales del proveedor de LLM: definí ANTHROPIC_API_KEY "
                "(o usá el panel de lectura automática, que no requiere API)")
        cliente = _cliente()

    mensajes = [{"role": "user", "content": f"{dossier.a_texto()}\n\n{dossier.pregunta}"}]
    texto, huerfanos = "", []
    for intento in range(1, reintentos + 2):
        texto = _pedir(cliente, mensajes)
        huerfanos = verificar(texto, dossier)
        if not huerfanos:
            lec = Lectura(texto=texto, verificado=True, intentos=intento)
            if usar_cache:
                _escribir_cache(h, lec)
            return lec
        if intento == reintentos + 1:
            break
        mensajes += [
            {"role": "assistant", "content": texto},
            {"role": "user", "content":
                "Estos números de tu respuesta no están en el dossier: "
                + ", ".join(huerfanos)
                + ". Reescribí la lectura usando únicamente los valores del dossier, con "
                  "sus unidades originales y sin reescalarlos. Si un número te hacía falta "
                  "para sostener una afirmación y no está, sacá la afirmación."},
        ]

    lec = Lectura(texto=texto, verificado=False, numeros_huerfanos=tuple(huerfanos),
                  intentos=reintentos + 1)
    if usar_cache:
        _escribir_cache(h, lec)
    return lec
