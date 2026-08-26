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
PROMPT_VERSION = "1"

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
otro para obtener un tercero.

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


def numeros_en(texto: str) -> list[tuple[str, float, int]]:
    """
    Todos los números del texto como (crudo, valor, decimales_escritos).
    `decimales_escritos` es lo que permite comparar con la misma precisión con la que
    el modelo escribió: si redondeó a un decimal, se lo compara redondeado a un decimal.
    """
    out: list[tuple[str, float, int]] = []
    for m in _RE_NUMERO.finditer(texto):
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
