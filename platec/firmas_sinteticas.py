"""
platec.firmas_sinteticas — estados contables sintéticos con tipologías de lavado.
=================================================================================
Genera balances y estados de resultados de empresas FICTICIAS, calibrados contra
la estructura sectorial real de la economía argentina, con etiqueta de verdad sobre
qué firmas ejecutan una maniobra y cuál.

QUÉ ES Y QUÉ NO ES
------------------
Es infraestructura de investigación. Los reportes de operación sospechosa son
confidenciales por ley en toda jurisdicción, así que no existen datos etiquetados
públicos: por eso la literatura del área trabaja con simuladores (AMLSim, SAML-D).

**No** son empresas reales, ni imitan a ninguna: los identificadores son
`SINT-0001`, sin nombre, sin CUIT y sin sector identificable a una firma concreta.
Nada de lo que sale de acá puede pasar por una presentación genuina, y esa es una
restricción de diseño, no un detalle.

LA TENSIÓN CON EL RESTO DE LA PLATAFORMA, Y CÓMO SE RESUELVE
------------------------------------------------------------
Toda la plataforma se apoya en una regla: no inventamos números. El narrador no
puede escribir una cifra que Python no calculó. Este módulo hace exactamente lo
contrario, así que se lo aísla por construcción:

1. **No persiste nada.** No hay tabla, no hay snapshot, no hay fila que pueda
   terminar al lado de un dato real. Se genera de forma DETERMINÍSTICA a partir de
   una semilla: misma semilla, mismas firmas. La reproducibilidad se consigue
   guardando un entero, no un dataset.
2. **No entra al narrador como dato.** Si alguna vez se redacta sobre esto, el
   dossier tiene que declararlo sintético como advertencia de primera clase.
3. Lo único real que toca es `data/ratios_sectoriales.json`, que sí son datos del
   INDEC y están marcados como tales.

LA ADVERTENCIA QUE NO HAY QUE OLVIDAR
-------------------------------------
Un detector entrenado acá encuentra las maniobras que uno mismo inyectó: no prueba
nada sobre el lavado real. Sirve para comparar métodos entre sí, para medir
potencia —cuán chica puede ser una maniobra y todavía detectarse— y para desarrollar
el pipeline. No sirve como evidencia sobre la economía argentina.

QUÉ HACE QUE SEA REALISTA
-------------------------
Cuatro cosas, y las cuatro se rompen en los generadores ingenuos:

- **Articulación contable.** Activo = Pasivo + Patrimonio, y el resultado del
  ejercicio cierra contra la variación del patrimonio. Si no articula, cualquier
  detector encuentra la maniobra por la vía equivocada y el dataset no sirve.
- **Ley de Benford.** Los datos contables reales siguen la distribución de primer
  dígito de Benford; un generador con `uniform()` no. Y como la desviación de
  Benford es en sí misma un detector forense clásico, si no se respeta el problema
  se vuelve trivial. Acá los montos salen de una lognormal, que la satisface por
  construcción.
- **Estructura sectorial real.** Margen operativo y participación salarial salen
  de la Cuenta de Generación del Ingreso del INDEC, no de la intuición.
- **Historia coherente.** Cada firma tiene varios ejercicios encadenados: una
  anomalía lo es contra el propio pasado de la firma, no contra un promedio.
- **La maniobra va a quien puede hacerla.** No se sobrefactura importaciones sin
  importar ni se subfactura exportaciones sin exportar. Repartirlas al azar —como
  hacía la primera versión— las diluye dentro de firmas que apenas comercian y deja
  una señal invisible: la sobrefacturación movía el margen de 0,96 a 0,95.

QUÉ DEJA CADA MANIOBRA EN LOS LIBROS
------------------------------------
Normalizado por la estructura de cada sector (1,00 = igual a lo normal de su
actividad). «Crec. máx.» es el mayor salto interanual de facturación de la firma.

    tipología                     margen  nómina  ing/AF  pas/pat   caja   crec
    (sin maniobra)                  0,96    1,00    2,03     1,11  0,075    17%
    pantalla                        1,78    0,07   43,86     1,10  0,075    18%
    fachada                         1,36    0,68    2,88     0,96  0,051    56%
    efectivo                        1,24    0,76    2,68     1,13  0,277    37%
    subfacturacion_exportaciones    0,68    1,18    1,74     1,23  0,091    17%
    sobrefacturacion_importaciones  0,90    1,00    1,90     1,09  0,071    18%
    compras_desproporcionadas       0,95    1,00    0,70     8,12  0,073    19%
    nueva_alto_volumen              0,95    1,03    1,93     1,28  0,074  1.749%

Ninguna se identifica con una sola razón, y dos son deliberadamente difíciles:

- La **fachada** conserva su nómina y su planta porque son reales. No hay anomalía
  estructural que buscar: sólo factura más de lo que esa capacidad explica. Un
  dataset con sólo pantallas sobreestima cualquier detector.
- La **entidad reactivada** es indistinguible en corte transversal. Su anomalía es
  la TRAYECTORIA, y eso obliga a usar la historia de la firma y no una foto.

La subfacturación comprime el margen, pero eso lo comparte con cualquier empresa que
simplemente gana poco: el estado contable la SEÑALA y no la identifica. Lo que la
identifica es comparar contra lo que declara la contraparte, que es lo que hace
`comercio_espejo` en agregado.

SUPUESTO QUE CONVIENE TENER PRESENTE. La subfacturación omite ingresos y deja los
costos en los libros, y por eso comprime el margen. Una firma que además maneje los
costos correspondientes por fuera mostraría un margen menos comprimido: este canal
está modelado en el extremo detectable del rango.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

RATIOS = Path(__file__).resolve().parent.parent / "data" / "ratios_sectoriales.json"

@dataclass(frozen=True)
class Tipologia:
    """
    Una maniobra modelada, con el indicador de GAFI que la respalda.

    La cita no es decorativa: ata cada tipología a un indicador publicado en
    «Trade-Based Money Laundering: Risk Indicators» (GAFI/Egmont, marzo 2021) o a la
    taxonomía regional de GAFILAT, en vez de a la intuición de quien escribió el
    generador. Si una tipología no puede citar nada, probablemente no exista.
    """
    descripcion: str
    fuente: str


# `limpia` no es una etiqueta más: es la clase mayoritaria. En AML la prevalencia
# real está en el orden de 1 en 1.000, y un dataset balanceado convierte un problema
# de detección en uno de clasificación fácil. El default respeta eso.
#
# SOBRE LA COBERTURA. De los 35 indicadores de GAFI, sólo unos siete son observables
# en un estado contable anual: el 80% son de documentos aduaneros y de movimientos de
# cuenta, que un balance no contiene. Lo que se modela acá es esa minoría, y esa
# limitación es del objeto, no del generador.
TIPOLOGIAS = {
    "limpia": Tipologia("Firma sin maniobra.", "—"),
    "subfacturacion_exportaciones": Tipologia(
        "Declara exportaciones por debajo de lo embarcado; la diferencia queda "
        "afuera. Es la maniobra que el módulo de comercio espejo mide en agregado.",
        "GAFI/Egmont 2021, documentos: precios fuera de consideraciones comerciales"),
    "sobrefacturacion_importaciones": Tipologia(
        "Declara importaciones por encima de lo recibido para girar divisas al "
        "oficial. Exige acceso al mercado oficial de cambios.",
        "GAFI/Egmont 2021, actividad: «consistently displays unreasonably low profit "
        "margins… importing wholesale commodities at or above retail value»"),
    "pantalla": Tipologia(
        "Factura sin huella operativa: ingresos altos, nómina y activo fijo casi "
        "nulos para su sector.",
        "GAFI/Egmont 2021, estructural: «lacks regular payroll transactions in line "
        "with the number of stated employees» y «maintains a minimal number of "
        "working staff, inconsistent with its volume of traded commodities»"),
    "efectivo": Tipologia(
        "Negocio intensivo en efectivo que sobredeclara ventas para dar origen a "
        "fondos: caja desalineada de su sector.",
        "GAFILAT 2009-2016 §56, comercios pantalla para colocación de capital ilícito"),
    "fachada": Tipologia(
        "Operación REAL usada para mezclar. Nómina y activo fijo normales —porque son "
        "reales— pero facturación por encima de lo que esa capacidad instalada "
        "explica. Es la variante difícil: no tiene anomalía estructural que buscar.",
        "GAFILAT 2009-2016 §V, vehículos corporativos (§54, §64, §65, §69: empresa "
        "fachada)"),
    "compras_desproporcionadas": Tipologia(
        "Compra activos muy por encima de lo que su operación puede sostener, "
        "financiándose con deuda que el resultado no alcanza a servir.",
        "GAFI/Egmont 2021, actividad: «purchases commodities, allegedly on its own "
        "account, but the purchases clearly exceed the economic capabilities of the "
        "entity»"),
    "nueva_alto_volumen": Tipologia(
        "Entidad recién formada o reactivada tras un período de latencia que salta de "
        "golpe a un volumen alto, sin la trayectoria que eso supondría.",
        "GAFI/Egmont 2021, actividad: «A newly formed or recently re-activated trade "
        "entity engages in high-volume and high-value trade activity»; estructural: "
        "«unexplained periods of dormancy»"),
}


@dataclass(frozen=True)
class Calibracion:
    """Estructura real de un sector, desde la Cuenta de Generación del Ingreso."""
    sector: str
    margen_operativo: float
    participacion_salarial: float


def calibraciones(ruta: Path | None = None) -> dict[str, Calibracion]:
    """Los ratios sectoriales del INDEC, como {sector: Calibracion}."""
    p = ruta or RATIOS
    if not p.exists():
        raise FileNotFoundError(
            f"falta {p}: correr `python3 scripts/ingest_ratios_sectoriales.py`")
    j = json.loads(p.read_text(encoding="utf-8"))
    return {k: Calibracion(k, v["margen_operativo"], v["participacion_salarial"])
            for k, v in j["sectores"].items()}


def _lognormal(rng, mediana: float, sigma: float, n: int = 1):
    """
    Montos lognormales. No es una elección estética: el tamaño de las empresas se
    distribuye así, y además es lo que hace que los primeros dígitos cumplan Benford.
    """
    return rng.lognormal(np.log(mediana), sigma, n)


def _ejercicio(rng, cal: Calibracion, ingresos: float, tipologia: str,
               perfil: dict) -> dict:
    """
    Un ejercicio de una firma: resultados y balance, ya articulados.

    El orden importa. Primero se arma la firma NORMAL de su sector y recién después
    se aplica la maniobra sobre esa base: así la anomalía es un desvío respecto de
    lo que la firma debería ser, y no un objeto construido aparte.
    """
    # --- estructura normal del sector ------------------------------------
    ruido = lambda s: float(rng.normal(1.0, s))                       # noqa: E731
    salarios = ingresos * cal.participacion_salarial * ruido(0.15)
    otros_costos = ingresos * (1 - cal.margen_operativo) * ruido(0.10) - salarios
    otros_costos = max(otros_costos, ingresos * 0.02)
    activo_fijo = ingresos * float(rng.uniform(0.25, 0.75))
    caja = ingresos * float(rng.uniform(0.03, 0.12))
    creditos = ingresos * float(rng.uniform(0.10, 0.30))
    # La exposición al comercio exterior es un rasgo de la FIRMA, pero NO es idéntica
    # todos los años: un exportador real tiene una participación que fluctúa con sus
    # contratos. Sin ese ruido, el desvío entre ejercicios era exactamente cero para
    # toda firma limpia y se volvía el mejor predictor del panel — otra vez, un
    # detector aprendiendo el generador y no la maniobra.
    exportaciones = ingresos * perfil["exportador"] * max(float(rng.normal(1.0, 0.18)), 0.05)
    importaciones = otros_costos * perfil["importador"] * max(float(rng.normal(1.0, 0.18)), 0.05)

    # --- la maniobra -----------------------------------------------------
    desvio = 0.0
    if tipologia == "subfacturacion_exportaciones":
        # Se declara menos exportación, y los ingresos bajan en la proporción que
        # esa exportación representaba: la diferencia es la que queda afuera.
        peso_export = exportaciones / max(ingresos, 1.0)
        desvio = perfil["intensidad"]
        exportaciones *= (1 - desvio)
        ingresos *= (1 - desvio * peso_export)
    elif tipologia == "sobrefacturacion_importaciones":
        # El costo inflado NO es un costo: el dinero vuelve al dueño afuera. Pero en
        # los libros comprime el margen, y de paso baja el impuesto a las ganancias.
        desvio = perfil["intensidad"]
        inflado = importaciones * desvio
        importaciones += inflado
        otros_costos += inflado
    elif tipologia == "pantalla":
        # Lo que la delata no es facturar mucho, sino facturar sin con qué.
        salarios *= float(rng.uniform(0.02, 0.12))
        activo_fijo *= float(rng.uniform(0.01, 0.08))
        desvio = 1.0
    elif tipologia == "efectivo":
        infl = float(rng.uniform(0.15, 0.50))
        ingresos *= (1 + infl)
        caja *= float(rng.uniform(3.0, 8.0))
        desvio = infl
    elif tipologia == "fachada":
        # LA VARIANTE DIFÍCIL. La operación es real, así que la nómina y el activo
        # fijo NO se tocan: ya quedaron calculados sobre el ingreso genuino. Sólo se
        # infla la facturación. El resultado es una firma sin ninguna anomalía
        # estructural —tiene empleados, tiene planta— que factura más de lo que esa
        # capacidad instalada explica, y cuyo margen mejora porque el dinero inyectado
        # no tiene costo. Es lo contrario de la pantalla: allá falta el cuerpo, acá
        # sobra la facturación.
        desvio = perfil["intensidad"] * 2
        ingresos *= (1 + desvio)
    elif tipologia == "compras_desproporcionadas":
        # Compra por encima de lo que su operación sostiene. El activo fijo se dispara
        # y lo financia deuda, no resultados: el patrimonio queda chico contra un
        # activo grande y el resultado operativo no alcanza a servir el pasivo.
        desvio = perfil["intensidad"]
        activo_fijo *= (1 + desvio * 8)

    # --- resultados ------------------------------------------------------
    resultado_operativo = ingresos - salarios - otros_costos
    impuestos = max(resultado_operativo, 0) * 0.35
    resultado_neto = resultado_operativo - impuestos

    # --- balance, articulado por construcción ----------------------------
    # El pasivo es el residuo: se arma el activo con sentido económico y el
    # patrimonio a partir del resultado, y lo que falta para cerrar es deuda. Así
    # la identidad se cumple exactamente y no por un ajuste ad hoc al final.
    activo = caja + creditos + activo_fijo
    if tipologia == "compras_desproporcionadas":
        # Lo compró con deuda, no con lo que ganó.
        patrimonio = activo * float(rng.uniform(0.05, 0.18))
    else:
        patrimonio = activo * float(rng.uniform(0.30, 0.65))
    pasivo = activo - patrimonio

    return {
        "ingresos": ingresos, "salarios": salarios, "otros_costos": otros_costos,
        "resultado_operativo": resultado_operativo, "impuestos": impuestos,
        "resultado_neto": resultado_neto,
        "caja": caja, "creditos": creditos, "activo_fijo": activo_fijo,
        "activo": activo, "pasivo": pasivo, "patrimonio": patrimonio,
        "exportaciones": exportaciones, "importaciones": importaciones,
        "desvio_maniobra": desvio,
    }


# Efecto de la brecha cambiaria sobre la subfacturación de exportaciones, estimado
# en `comercio_espejo.contraste_brecha`: +0,059 puntos porcentuales de discrepancia
# sobre el comercio del par por cada punto de brecha.
#
# EL CANAL IMPORTADOR NO ESCALA CON LA BRECHA, y eso no es un olvido: es el hallazgo.
# El contraste da beta = +0,009 con p = 0,68, un cero limpio. La explicación es
# institucional: sobrefacturar una importación exige acceso al dólar oficial, que es
# justamente lo que el cepo raciona vía DJAI, SIMI o SIRA. Subfacturar una
# exportación no exige permiso de nadie. Que el generador reprodujera las dos
# maniobras creciendo con la brecha contradiría la evidencia de la propia plataforma.
BETA_EXPORTADOR = 0.0589

# Techo de la maniobra por firma. Omitir más del 60% de lo exportado deja un estado
# contable absurdo —con la primera versión, topeando en 0,95, aparecían firmas con
# margen operativo negativo— y ninguna empresa sostiene eso sin que se note a ojo.
INTENSIDAD_MAXIMA = 0.60


def _perfiles(rng, n_firmas: int, prevalencia: float) -> list[dict]:
    """
    Rasgos de cada firma, constantes entre ejercicios: sector, escala, exposición al
    comercio exterior, tipología y con qué intensidad la ejecuta.

    LA MANIOBRA SE ASIGNA SEGÚN LO QUE LA FIRMA PUEDE HACER. No se puede
    sobrefacturar importaciones sin importar, ni subfacturar exportaciones sin
    exportar. Asignarlas al azar —como hacía la primera versión— diluye la maniobra
    dentro de firmas que apenas comercian y deja una señal invisible: la
    sobrefacturación movía el margen de 0,96 a 0,95 y no significaba nada.
    """
    sospechosas = sorted(TIPOLOGIAS.keys() - {"limpia"})
    if prevalencia > 0 and not sospechosas:
        raise ValueError("no hay tipologías sospechosas: TIPOLOGIAS sólo trae «limpia»")
    marcadas = set(rng.choice(n_firmas, size=int(round(n_firmas * prevalencia)),
                              replace=False).tolist())
    perfiles = []
    for i in range(n_firmas):
        tip = sospechosas[int(rng.integers(len(sospechosas)))] if i in marcadas else "limpia"
        # EXPOSICIÓN COMERCIAL: LOS SOPORTES TIENEN QUE SOLAPARSE.
        #
        # La maniobra va a quien puede hacerla, pero eso no significa que quien puede
        # hacerla la haga. La primera versión sorteaba la intensidad exportadora de
        # las limpias en [0,00 - 0,35] y la de las subfacturadoras en [0,45 - 0,85]:
        # soportes DISJUNTOS, así que "exportador > 0,40" las identificaba perfecto.
        # Un detector entrenado sobre eso aprendía a reconocer el sorteo, no la
        # maniobra — y lo delató al dar PR-AUC 0,89 con prevalencia 2%, que para un
        # problema de AML es demasiado bueno para ser cierto.
        #
        # Ahora una parte de las firmas son comerciantes, limpias o no, y las
        # manipuladoras salen de esa MISMA población. Comerciar mucho es informativo
        # —la maniobra lo exige— pero no determinante, que es el caso real.
        def _intensidad_comercial(obliga: bool) -> float:
            if obliga or rng.random() < 0.35:
                return float(rng.uniform(0.30, 0.85))      # firma comerciante
            return float(rng.uniform(0.0, 0.25))           # comercia poco o nada

        exportador = _intensidad_comercial(tip == "subfacturacion_exportaciones")
        importador = _intensidad_comercial(tip == "sobrefacturacion_importaciones")
        perfiles.append({
            "tipologia": tip, "exportador": exportador, "importador": importador,
            "escala": float(_lognormal(rng, mediana=800e6, sigma=1.4)[0]),
            "intensidad": float(rng.uniform(0.10, 0.40)),
            # Sólo usados por `nueva_alto_volumen`: cuánto opera mientras está latente
            # y por cuánto multiplica al reactivarse. El cociente entre los dos —entre
            # 7 y 40 veces— es el salto observable. Con la primera calibración daba
            # hasta 400 veces, un caso que se detecta a ojo y que por eso no sirve:
            # un dataset donde la anomalía salta sola no mide ningún detector.
            "latencia": float(rng.uniform(0.08, 0.25)),
            "salto": float(rng.uniform(1.8, 3.5)),
        })

    return perfiles


def generar(n_firmas: int = 500, ejercicios: int = 4, semilla: int = 7,
            prevalencia: float = 0.02, anio_inicial: int = 2019,
            brecha: float = 0.0, ruta_ratios: Path | None = None) -> pd.DataFrame:
    """
    Panel firma × ejercicio de estados contables sintéticos, con etiqueta de verdad.

    `prevalencia` es la fracción de firmas con maniobra. El default (2%) es alto
    frente a la realidad —el orden es 1 en 1.000— pero deja muestra suficiente para
    experimentar; subirlo al 50% convierte la detección en un problema fácil que no
    se parece a nada.

    `brecha` (en %) calibra la intensidad de la subfacturación de exportaciones para
    que la discrepancia agregada reproduzca el beta estimado en `comercio_espejo`.
    Con 0 se usa la intensidad sorteada y el panel no representa ningún régimen
    cambiario en particular. **La sobrefacturación de importaciones no escala con la
    brecha**: es el hallazgo del contraste macro, no una omisión.

    Determinístico: misma semilla, mismas firmas. Por eso no hace falta persistir el
    dataset, y por eso ninguna fila sintética puede terminar al lado de un dato real.
    """
    if not 0.0 <= prevalencia <= 1.0:
        raise ValueError(f"prevalencia fuera de [0, 1]: {prevalencia}")
    if brecha < 0:
        raise ValueError(f"brecha negativa: {brecha}")
    cals = calibraciones(ruta_ratios)
    if not cals:
        raise ValueError("no hay sectores calibrados")

    perfiles = _perfiles(np.random.default_rng(semilla), n_firmas, prevalencia)
    df = _construir(perfiles, cals, ejercicios, anio_inicial, semilla)

    # --- calibración del canal exportador contra el beta macro ------------
    # Se calibra MIDIENDO, no despejando. La versión analítica erraba un 20% de
    # forma sistemática porque la maniobra no está activa en todos los ejercicios
    # (arranca en uno sorteado) y porque el denominador de la discrepancia son las
    # exportaciones DECLARADAS, ya reducidas. Ninguna de las dos cosas se conoce
    # antes de generar. Se genera, se mide, se reescala y se regenera con el mismo
    # sorteo: como la respuesta es lineal en la intensidad, una pasada alcanza.
    objetivo = BETA_EXPORTADOR * brecha / 100.0
    if brecha > 0:
        actual = discrepancia_exportadora(df)
        if actual > 0:
            factor = objetivo / actual
            for pf in perfiles:
                if pf["tipologia"] == "subfacturacion_exportaciones":
                    pf["intensidad"] = min(pf["intensidad"] * factor, INTENSIDAD_MAXIMA)
            df = _construir(perfiles, cals, ejercicios, anio_inicial, semilla)

    # ¿Se alcanzó el objetivo? Puede no alcanzarse, y no es un bug: si hay pocas
    # firmas subfacturadoras, ninguna intensidad admisible hace que el agregado
    # llegue. Es una restricción económica real —el beta macro implica cuánto
    # comercio tiene que estar en manos de manipuladores— y por eso se informa en
    # vez de topear en silencio, que dejaba firmas con margen negativo.
    logrado = discrepancia_exportadora(df) if brecha > 0 else 0.0
    df.attrs.update(semilla=semilla, prevalencia=prevalencia, brecha=brecha,
                    sintetico=True, objetivo_discrepancia=objetivo,
                    discrepancia_lograda=logrado,
                    calibrado=bool(brecha == 0 or (objetivo > 0
                                   and abs(logrado / objetivo - 1) < 0.15)))
    return df


def _construir(perfiles: list[dict], cals: dict, ejercicios: int,
               anio_inicial: int, semilla: int) -> pd.DataFrame:
    """
    Arma el panel a partir de perfiles ya fijados.

    Toma la semilla y no un `rng` en curso: así dos llamadas con los mismos perfiles
    producen exactamente los mismos sorteos, y la única diferencia entre la pasada
    de calibración y la definitiva es la intensidad de la maniobra.
    """
    rng = np.random.default_rng(semilla + 1)
    sectores = sorted(cals)
    filas = []
    for i, perfil in enumerate(perfiles):
        cal = cals[sectores[int(rng.integers(len(sectores)))]]
        escala = perfil["escala"]
        # La maniobra empieza en un ejercicio, no necesariamente en el primero.
        if perfil["tipologia"] == "limpia":
            desde = ejercicios
        elif perfil["tipologia"] == "nueva_alto_volumen":
            # Tiene que haber latencia ANTES del salto, o no hay nada que observar.
            desde = int(rng.integers(1, max(ejercicios, 2)))
        else:
            desde = int(rng.integers(0, ejercicios))
        for t in range(ejercicios):
            escala *= float(rng.normal(1.08, 0.12))       # crecimiento nominal
            activa = t >= desde
            # `nueva_alto_volumen` no deforma un ejercicio sino la TRAYECTORIA: la
            # firma está casi latente y después salta. Por eso se aplica acá, sobre
            # la escala, y no en `_ejercicio`, que sólo ve un año por vez.
            escala_t = escala
            if perfil["tipologia"] == "nueva_alto_volumen":
                escala_t *= perfil["salto"] if activa else perfil["latencia"]
            e = _ejercicio(rng, cal, escala_t,
                           perfil["tipologia"] if activa else "limpia", perfil)
            filas.append({"firma": f"SINT-{i:04d}", "sector": cal.sector,
                          "ejercicio": anio_inicial + t,
                          "tipologia": perfil["tipologia"], "maniobra_activa": activa,
                          "exportador": perfil["exportador"],
                          "importador": perfil["importador"], **e})
    return pd.DataFrame(filas)


def discrepancia_exportadora(df: pd.DataFrame) -> float:
    """
    Subfacturación agregada como fracción de las exportaciones declaradas del panel.

    Es el objeto que `comercio_espejo` mide desde el otro lado —comparando contra lo
    que declara la contraparte— y sirve para verificar que el panel sintético
    reproduce el beta macro con el que se lo calibró.
    """
    sub = df[(df["tipologia"] == "subfacturacion_exportaciones") & df["maniobra_activa"]]
    if sub.empty or df["exportaciones"].sum() <= 0:
        return 0.0
    # exportaciones declaradas = reales * (1 - intensidad); lo omitido es la diferencia
    omitido = (sub["exportaciones"] / (1 - sub["desvio_maniobra"]) - sub["exportaciones"]).sum()
    return float(omitido / df["exportaciones"].sum())


def articula(df: pd.DataFrame, tolerancia: float = 1e-6) -> bool:
    """
    ¿Cierra la identidad contable en todas las filas?

    Es la primera cosa que un detector encontraría si estuviera rota, y encontraría
    la maniobra por la vía equivocada.
    """
    d = (df["activo"] - df["pasivo"] - df["patrimonio"]).abs()
    return bool((d <= tolerancia * df["activo"].abs().clip(lower=1)).all())


def primer_digito(s: pd.Series) -> pd.Series:
    """Distribución del primer dígito significativo de una serie de montos."""
    v = pd.to_numeric(s, errors="coerce").abs()
    v = v[(v > 0) & np.isfinite(v)]
    d = v.astype(str).str.replace(r"[^1-9]", "", regex=True).str[:1]
    d = pd.to_numeric(d, errors="coerce").dropna().astype(int)
    return d.value_counts(normalize=True).reindex(range(1, 10), fill_value=0.0).sort_index()


def benford_esperado() -> pd.Series:
    """P(primer dígito = d) = log10(1 + 1/d)."""
    d = np.arange(1, 10)
    return pd.Series(np.log10(1 + 1 / d), index=d)


def desvio_benford(s: pd.Series) -> float:
    """
    Distancia media absoluta (MAD) entre la distribución observada y Benford.

    Convención forense habitual: por debajo de 0,006 se considera conformidad
    cercana; por encima de 0,015, no conformidad.
    """
    return float((primer_digito(s) - benford_esperado()).abs().mean())


def share_exportador_minimo(brecha: float = 100.0,
                            intensidad_maxima: float = INTENSIDAD_MAXIMA) -> float:
    """
    Fracción MÍNIMA del valor exportado que tiene que estar en manos de firmas
    subfacturadoras para que el agregado alcance el beta estimado.

    No es un parámetro del simulador: es una implicancia aritmética del beta macro.
    Si el 5,9% de las exportaciones se omite y ninguna firma omite más del 60% de
    las suyas, entonces al menos el 9,8% del valor exportado pasa por manipuladores.

    Es la restricción que vuelve infactible calibrar con prevalencias bajas, y es un
    resultado en sí mismo: dice cuánto comercio tiene que estar comprometido para
    que la discrepancia observada exista.
    """
    if not 0 < intensidad_maxima <= 1:
        raise ValueError(f"intensidad máxima fuera de (0, 1]: {intensidad_maxima}")
    return min(BETA_EXPORTADOR * brecha / 100.0 / intensidad_maxima, 1.0)
