"""
platec.gobiernos — comparación de indicadores entre períodos presidenciales.
============================================================================
Responde "¿cómo varió X en los últimos gobiernos?" sin caer en las dos trampas
que arruinan esa comparación en Argentina:

1. **Nominal.** Comparar la base monetaria de 2004 con la de 2026 en pesos es
   comparar inflación, no política monetaria. Acá todo lo que está en pesos se
   normaliza por **PIB nominal** (numerador y denominador en pesos del mismo
   trimestre, así que no hace falta ningún deflactor) o se pasa a **USD**.

2. **Deflactar con un índice no creíble.** El IPC oficial 2007-2015 está marcado
   INTERVENIDO en `quality_periods` y `data.get_series` lo excluye por defecto.
   Usarlo como deflactor haría que ese tramo se vea artificialmente bien en
   términos reales. Por eso la normalización por PBI es la vía principal.

Las series arrancan en fechas distintas, así que ningún gobierno tiene todos los
indicadores. `cobertura()` mide qué fracción del período tiene dato y la tabla
devuelve NaN —no un promedio de media docena de meses— cuando no alcanza.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from platec import data

# ---------------------------------------------------------------------------
# Periodización
# ---------------------------------------------------------------------------
# Fechas de traspaso de mando. El tramo 2001-12-20 -> 2003-05-25 agrupa la crisis
# (Puerta, Rodríguez Saá, Camaño, Duhalde): son cinco presidentes en dieciocho
# meses y separarlos daría períodos de días, sin sentido estadístico.
GOBIERNOS: list[tuple[str, str, str | None]] = [
    ("Menem II",       "1995-07-08", "1999-12-10"),
    ("De la Rúa",      "1999-12-10", "2001-12-20"),
    ("Crisis 2001-03", "2001-12-20", "2003-05-25"),
    ("N. Kirchner",    "2003-05-25", "2007-12-10"),
    ("CFK I",          "2007-12-10", "2011-12-10"),
    ("CFK II",         "2011-12-10", "2015-12-10"),
    ("Macri",          "2015-12-10", "2019-12-10"),
    ("A. Fernández",   "2019-12-10", "2023-12-10"),
    ("Milei",          "2023-12-10", None),
]

# Cobertura mínima del período para reportar un agregado. Por debajo, la tabla
# devuelve NaN: un "promedio" de tres meses sobre un mandato de cuatro años no
# es el promedio del mandato, es una foto disfrazada de serie.
COBERTURA_MINIMA = 0.60


@dataclass(frozen=True)
class Periodo:
    nombre: str
    desde: pd.Timestamp
    hasta: pd.Timestamp      # fin efectivo (hoy si el mandato está en curso)
    en_curso: bool

    @property
    def anios(self) -> float:
        return (self.hasta - self.desde).days / 365.25

    def recortar(self, s: pd.Series) -> pd.Series:
        if not isinstance(s.index, pd.DatetimeIndex):
            return s.iloc[:0]
        return s[(s.index >= self.desde) & (s.index < self.hasta)].dropna()


def periodos(desde: str | None = None) -> list[Periodo]:
    """Los mandatos como objetos, con el que está en curso cerrado al día de hoy."""
    hoy = pd.Timestamp.today().normalize()
    out = []
    for nombre, d, h in GOBIERNOS:
        d = pd.Timestamp(d)
        en_curso = h is None
        h = hoy if en_curso else pd.Timestamp(h)
        if desde and h <= pd.Timestamp(desde):
            continue
        out.append(Periodo(nombre, d, h, en_curso))
    return out


def etiquetar(s: pd.Series) -> pd.Series:
    """Serie de etiquetas de gobierno alineada al índice de `s` (NaN fuera de rango)."""
    out = pd.Series(pd.NA, index=s.index, dtype="object")
    for p in periodos():
        out[(s.index >= p.desde) & (s.index < p.hasta)] = p.nombre
    return out


# ---------------------------------------------------------------------------
# Normalizaciones
# ---------------------------------------------------------------------------
def pib_mensual() -> pd.Series:
    """
    PIB nominal a tasa anual, llevado a frecuencia mensual.

    OJO CON LA UNIDAD. La serie `9.2_PPC_2004_T_22` viene etiquetada "Millones de
    pesos corrientes" con frecuencia trimestral, lo que se lee naturalmente como
    "el PIB de ese trimestre". No lo es: **ya viene anualizada**, cada trimestre
    trae el PIB a tasa anual. Sumar los cuatro trimestres —el reflejo obvio— da
    4,3x el PIB real y hunde todos los ratios a un cuarto de su valor.

    Control cruzado que lo prueba (promedio de los 4 trimestres / TC mayorista):
    2010 -> 0,42 · 2019 -> 0,45 · 2024 -> 0,63 billones de USD, que es el PIB
    efectivo de Argentina en esos años. Sumando daría 1,70 / 1,80 / 2,53.

    Se interpola linealmente a meses en vez de arrastrar el último valor: un
    escalón trimestral en el denominador mete saltos artificiales en el ratio
    justo en los meses de empalme.
    """
    pib = data.get_series("pib_corriente")
    idx = pd.date_range(pib.index.min(), pib.index.max() + pd.offsets.MonthEnd(3),
                        freq="MS")
    return pib.reindex(pib.index.union(idx)).interpolate("time").reindex(idx).dropna()


def pct_pib(s: pd.Series, tipo: str = "stock") -> pd.Series:
    """
    Serie en pesos -> % del PIB.

    tipo='stock' : el valor es un saldo (base monetaria). Se divide por el PIB
                   anualizado directamente.
    tipo='flujo' : el valor es un flujo mensual (resultado primario, recaudación).
                   Se acumula a 12 meses antes de dividir, para que el ratio sea
                   comparable con el PIB anual y no doce veces más chico.
    """
    if tipo not in ("stock", "flujo"):
        raise ValueError("tipo debe ser 'stock' o 'flujo'")
    s = s.resample("MS").last() if tipo == "stock" else s.resample("MS").sum()
    if tipo == "flujo":
        s = s.rolling(12).sum()
    return (s / pib_mensual() * 100).dropna()


def en_usd(s: pd.Series, tc: str = "tc_mayorista") -> pd.Series:
    """
    Serie en pesos -> USD al tipo de cambio oficial de referencia.

    Alternativa al % del PBI para stocks monetarios, y la única disponible antes
    de 2004 (el PIB de la API arranca ahí). Advertencia: bajo cepo el oficial es
    un precio administrado, así que la conversión sobrestima el valor en dólares
    de 2012-2015 y 2020-2023. Para esos tramos contrastar con el CCL.
    """
    d = pd.concat({"v": s, "tc": data.get_series(tc)}, axis=1).ffill().dropna()
    return (d["v"] / d["tc"]).rename(s.name)


# ---------------------------------------------------------------------------
# Agregación por gobierno
# ---------------------------------------------------------------------------
def cobertura(s: pd.Series, p: Periodo) -> float:
    """
    Fracción del mandato efectivamente cubierta por la serie.

    Se mide como el TRAMO que va de la primera a la última observación dentro del
    período, dividido por el largo del período — no como cantidad de meses con
    dato. Contar meses castiga a las series de baja frecuencia por existir: el
    desempleo es trimestral, así que cubre un mandato entero con un dato cada
    tres meses y un conteo mensual le daría 0,33 de cobertura, por debajo de
    cualquier umbral razonable. El tramo mide lo que importa: si la serie abarca
    el mandato o solo una punta.

    Al tramo se le suma el espaciado típico de la serie: la última observación
    REPRESENTA a su período, no lo cierra. Sin ese ajuste una serie trimestral que
    cubre un mandato entero mide 0,94 en vez de 1,0, porque el último trimestre
    aporta su fecha de inicio y no la de fin.
    """
    v = p.recortar(s)
    if len(v) < 2:
        return 0.0
    largo = (p.hasta - p.desde).days
    if not largo:
        return 0.0
    espaciado = float(v.index.to_series().diff().dt.days.median() or 0)
    return min(((v.index[-1] - v.index[0]).days + espaciado) / largo, 1.0)


def _var_anualizada(v: pd.Series, anios: float) -> float:
    """Tasa anualizada de la variación punta a punta. Requiere serie positiva."""
    if len(v) < 2 or anios <= 0 or v.iloc[0] <= 0 or v.iloc[-1] <= 0:
        return np.nan
    return ((v.iloc[-1] / v.iloc[0]) ** (1 / anios) - 1) * 100


def por_gobierno(s: pd.Series, como: str = "promedio",
                 cobertura_minima: float = COBERTURA_MINIMA) -> pd.DataFrame:
    """
    Resume una serie por mandato.

    como : 'promedio' | 'inicio' | 'fin' | 'cambio' (fin - inicio) |
           'var_anual' (tasa anualizada punta a punta) | 'acumulado' (suma) |
           'maximo' | 'minimo'

    Devuelve una fila por gobierno con el valor, la cobertura y los meses con
    dato. Si la cobertura no llega a `cobertura_minima`, el valor es NaN.
    """
    calc = {
        "promedio":  lambda v, a: v.mean(),
        "inicio":    lambda v, a: v.iloc[0],
        "fin":       lambda v, a: v.iloc[-1],
        "cambio":    lambda v, a: v.iloc[-1] - v.iloc[0],
        "var_anual": lambda v, a: _var_anualizada(v, a),
        "acumulado": lambda v, a: v.sum(),
        "maximo":    lambda v, a: v.max(),
        "minimo":    lambda v, a: v.min(),
    }
    if como not in calc:
        raise ValueError(f"`como` inválido: {como}. Opciones: {sorted(calc)}")

    filas = []
    for p in periodos():
        v = p.recortar(s)
        cob = cobertura(s, p)
        val = calc[como](v, p.anios) if len(v) and cob >= cobertura_minima else np.nan
        filas.append({"gobierno": p.nombre, "valor": val, "cobertura": round(cob, 2),
                      "meses": len(v.resample("MS").last().dropna()),
                      "desde": p.desde.date(), "hasta": p.hasta.date(),
                      "en_curso": p.en_curso})
    return pd.DataFrame(filas).set_index("gobierno")


# Qué se muestra en la tabla comparativa: (etiqueta, serie, transformación, agregación).
# `trans` es None (serie tal cual), 'pct_pib_stock', 'pct_pib_flujo' o 'usd'.
METRICAS: list[tuple[str, str, str | None, str]] = [
    ("Base monetaria (% PBI, fin)",      "base_monetaria", "pct_pib_stock", "fin"),
    ("Base monetaria (% PBI, cambio)",   "base_monetaria", "pct_pib_stock", "cambio"),
    ("Reservas BCRA (M USD, fin)",       "reservas",       None,            "fin"),
    ("Reservas BCRA (M USD, cambio)",    "reservas",       None,            "cambio"),
    ("Devaluación oficial (% anual)",    "tc_mayorista",   None,            "var_anual"),
    ("Riesgo país (pb, promedio)",       "riesgo_pais",    None,            "promedio"),
    ("Riesgo país (pb, máximo)",         "riesgo_pais",    None,            "maximo"),
    ("Resultado primario (% PBI, prom.)", "resultado_primario", "pct_pib_flujo", "promedio"),
    ("Recaudación (% PBI, promedio)",    "recaudacion_total",  "pct_pib_flujo", "promedio"),
    ("Exportaciones (M USD, promedio)",  "exportaciones",  None,            "promedio"),
    ("Saldo comercial (M USD, acum.)",   None,             "saldo",         "acumulado"),
    ("EMAE (var. % anual)",              "emae_original",  None,            "var_anual"),
    ("Desempleo (%, promedio)",          "desempleo",      None,            "promedio"),
    ("Inflación mensual (%, promedio)",  "inflacion_mensual", None,         "promedio"),
]


def _serie_transformada(sid: str | None, trans: str | None) -> pd.Series:
    if trans == "saldo":
        d = data.get_frame(["exportaciones", "importaciones"], freq="M").dropna()
        return (d["exportaciones"] - d["importaciones"]).rename("saldo_comercial")
    s = data.get_series(sid)
    if trans == "pct_pib_stock":
        return pct_pib(s, "stock")
    if trans == "pct_pib_flujo":
        return pct_pib(s, "flujo")
    if trans == "usd":
        return en_usd(s)
    return s


def tabla_comparativa(metricas: list | None = None,
                      cobertura_minima: float = COBERTURA_MINIMA) -> pd.DataFrame:
    """
    La tabla completa: una fila por métrica, una columna por gobierno.

    Las celdas sin cobertura suficiente quedan en NaN. Eso es información, no un
    defecto: muestra de un vistazo que el riesgo país arranca en 1999, el PIB en
    2004 y el resultado primario en 2016, así que ninguna comparación "desde
    Menem hasta hoy" es posible para todos los indicadores a la vez.
    """
    filas = {}
    for etiqueta, sid, trans, como in (metricas or METRICAS):
        try:
            s = _serie_transformada(sid, trans)
        except KeyError:
            continue
        r = por_gobierno(s, como=como, cobertura_minima=cobertura_minima)
        filas[etiqueta] = r["valor"]
    return pd.DataFrame(filas).T


def cobertura_matriz(metricas: list | None = None) -> pd.DataFrame:
    """La misma grilla que `tabla_comparativa` pero con la cobertura de cada celda."""
    filas = {}
    for etiqueta, sid, trans, como in (metricas or METRICAS):
        try:
            s = _serie_transformada(sid, trans)
        except KeyError:
            continue
        filas[etiqueta] = por_gobierno(s, como=como)["cobertura"]
    return pd.DataFrame(filas).T
