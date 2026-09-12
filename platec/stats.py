"""
platec.stats — transformaciones estadísticas estándar (sección 9 del documento).
================================================================================
Funciones puras sobre pd.Series/DataFrame: no tocan la base. Cubren variaciones,
medias móviles, detección de outliers y deflactación a términos reales.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Períodos por año según frecuencia, para variaciones interanuales
_PERIODOS_ANUALES = {"D": 252, "M": 12, "Q": 4}


def variacion(s: pd.Series, periodos: int = 1) -> pd.Series:
    """Variación porcentual respecto de `periodos` atrás (en %)."""
    return s.pct_change(periods=periodos) * 100


def var_intermensual(s: pd.Series) -> pd.Series:
    """Variación respecto del período inmediato anterior (%). Para series mensuales = mensual."""
    return variacion(s, 1)


def var_interanual(s: pd.Series, freq: str | None = None) -> pd.Series:
    """
    Variación interanual (%). Usa el nº de períodos por año según la frecuencia
    (freq='M'->12, 'Q'->4, 'D'->252). Si no se pasa, se toma de s.attrs['frequency'].
    """
    freq = freq or s.attrs.get("frequency", "M")
    return variacion(s, _PERIODOS_ANUALES[freq])


def media_movil(s: pd.Series, ventana: int = 3, centrada: bool = False) -> pd.Series:
    """Promedio móvil de `ventana` períodos."""
    return s.rolling(ventana, center=centrada, min_periods=ventana).mean()


def zscore(s: pd.Series, ventana: int | None = None) -> pd.Series:
    """
    Z-score. Si `ventana` es None usa media/desvío de toda la muestra; si se pasa,
    usa una ventana móvil (z-score rolling, útil en series con nivel cambiante).
    """
    if ventana is None:
        return (s - s.mean()) / s.std(ddof=0)
    mu = s.rolling(ventana, min_periods=ventana).mean()
    sd = s.rolling(ventana, min_periods=ventana).std(ddof=0)
    return (s - mu) / sd


def outliers(s: pd.Series, umbral: float = 3.0, ventana: int | None = None) -> pd.Series:
    """Máscara booleana: True donde |z-score| supera `umbral`."""
    return zscore(s, ventana=ventana).abs() > umbral


def deflactar(nominal: pd.Series, ipc: pd.Series, base=None) -> pd.Series:
    """
    Lleva una serie nominal a términos reales usando un índice de precios (IPC).
    real_t = nominal_t / (ipc_t / ipc_base). Ambas deben compartir frecuencia/índice.
    `base`: fecha o etiqueta para normalizar el IPC (por defecto, primer valor común).

    NOTA: el tipo de cambio REAL bilateral propio requiere además precios externos
    (ej. CPI de EE.UU. vía FRED). Esto deflacta solo por precios locales — es una
    medida de la serie en pesos constantes, no un RER bilateral completo.
    """
    ipc_al = ipc.reindex(nominal.index).ffill()
    ipc_base = ipc_al.loc[base] if base is not None else ipc_al.dropna().iloc[0]
    return nominal / (ipc_al / ipc_base)


def brecha(paralelo: pd.Series, oficial: pd.Series) -> pd.Series:
    """Brecha cambiaria (%) entre una cotización paralela y el oficial, alineadas por fecha."""
    df = pd.concat([paralelo, oficial], axis=1).dropna()
    return (df.iloc[:, 0] / df.iloc[:, 1] - 1) * 100


def resumen(s: pd.Series) -> dict:
    """Resumen rápido: último valor, fecha, variación intermensual e interanual."""
    s = s.dropna()
    return {
        "ultimo": round(float(s.iloc[-1]), 4),
        "fecha": s.index[-1].date().isoformat(),
        "var_periodo_%": round(float(variacion(s, 1).iloc[-1]), 2),
        "var_interanual_%": round(float(var_interanual(s).iloc[-1]), 2)
        if len(s) > _PERIODOS_ANUALES.get(s.attrs.get("frequency", "M"), 12) else None,
    }


# ---------------------------------------------------------------------------
# Retornos con cortes: cuando el índice se redefine, la variación no es un dato
# ---------------------------------------------------------------------------
# El EMBI+ Argentina tiene días en los que su valor cambia porque cambió QUÉ MIDE,
# no porque se haya movido el mercado. Al liquidarse un canje, los bonos en default
# salen del índice y entran los nuevos: el 13 de junio de 2005 el riesgo país pasa
# de 6.606 a 794 puntos básicos en una rueda, y el 10 de septiembre de 2020 de 2.120
# a 1.101. En log-diferencias eso es un retorno de -212% y otro de -65%, que no son
# movimientos de precio sino una recomposición del índice.
#
# POR QUÉ NO ALCANZA UN FILTRO DE OUTLIERS. El 12 de agosto de 2019 —el lunes
# después de las PASO— el riesgo país salta +52% en un día. Estadísticamente es tan
# extremo como una recomposición, y es un movimiento de mercado absolutamente real:
# el dato más informativo de toda la serie. Una regla automática por z-score los
# borraría a los dos. Por eso las fechas se listan a mano, con el evento que las
# justifica, igual que el tramo INTERVENIDO del IPC: es conocimiento del dominio,
# no un test.
#
# QUÉ SE ROMPE Y QUÉ NO. El NIVEL de esos días es correcto y se conserva; lo que no
# existe es la VARIACIÓN entre el día anterior y ese día, porque une dos objetos
# distintos. Se devuelve NaN, no cero: un cero diría "no se movió", que es falso.
RECOMPOSICIONES_EMBI = {
    "2005-06-13": "liquidación del canje I: los bonos en default salen del índice",
    "2005-06-30": "recomposición posterior al canje I",
    "2020-09-10": "liquidación del canje 2020",
}
# La reapertura del canje de 2010 NO produjo salto en esta serie (verificado sobre
# los datos: ningún movimiento mayor al 15% en junio de 2010). No está en la lista
# porque no hizo falta, no por olvido.


def log_dif(s: pd.Series, cortes=(), escala: float = 100.0) -> pd.Series:
    """
    Diferencia de logaritmos (×100), con los retornos de `cortes` puestos en NaN.

    `cortes` son fechas en las que la serie cambió de definición: el retorno que
    cruza ese día une dos objetos distintos y no es un dato. Devuelve NaN y no cero
    porque un cero afirmaría que no hubo movimiento.

    Con `cortes` vacío es una log-diferencia común.
    """
    d = np.log(s.astype(float)).diff() * escala
    for fecha in cortes:
        f = pd.Timestamp(fecha)
        if f in d.index:
            d.loc[f] = np.nan
    return d


# ---------------------------------------------------------------------------
# Tipo de cambio real bilateral
# ---------------------------------------------------------------------------
# TCR = e · P* / P   —   e en ARS/USD, P* precios externos, P precios locales.
# Sube = depreciación real = más competitivo.
#
# CUIDADO CON DÓNDE SE USA. Es un INDICADOR, no un regresor para el pass-through.
# En log-diferencias vale
#
#     Δlog(TCR) = Δlog(e) + π* − π
#
# así que regresar la inflación π contra Δlog(TCR) pone a π de los DOS LADOS de la
# ecuación. El coeficiente que sale mezcla el pass-through con un término mecánico
# de −var(π) y no se puede leer como una elasticidad. Medido en esta muestra da
# +0,062 (p = 0,10), pero eso es una casualidad: los dos términos casi se cancelan.
# La prueba de que no dice nada es que el MISMO test ignorando los precios externos
# da +0,060 — la «relación» no depende del dato que se agregó.
#
# Para el pass-through, lo que corresponde es deflactar el tipo de cambio SÓLO por
# precios externos (`e · P*`): saca la inflación ajena sin meter la propia del lado
# derecho. Medido acá, mueve el traslado a 6 meses de 53,8% a 54,7% — noventa
# centésimas, porque la inflación de EE.UU. es apenas el 7% de la devaluación
# argentina. Chico, pero ahora es un número y no un supuesto.
def tcr_bilateral(tc: pd.Series, precios_locales: pd.Series, precios_externos: pd.Series,
                  base=None) -> pd.Series:
    """
    Tipo de cambio real bilateral, en índice con base = 100 en `base`.

    `base` puede ser una fecha o None; con None se usa el promedio de todo el
    período común, que evita que la lectura dependa de qué mes se eligió de ancla.

    Las tres series se alinean por fecha y se recorta a la intersección: un TCR
    calculado sobre fechas donde falta un componente sería una invención.
    """
    df = pd.concat({"tc": tc, "p": precios_locales, "pe": precios_externos},
                   axis=1).dropna()
    if df.empty:
        raise ValueError("las tres series no se solapan en ninguna fecha")
    real = df["tc"] * df["pe"] / df["p"]
    ancla = real.loc[base] if base is not None else real.mean()
    s = real / float(ancla) * 100
    s.name = "tcr_bilateral"
    return s


def tc_deflactado_externo(tc: pd.Series, precios_externos: pd.Series) -> pd.Series:
    """
    Tipo de cambio nominal llevado a precios externos constantes (`e · P*`).

    Es el regresor que corresponde para el pass-through: le saca al tipo de cambio
    la inflación del país emisor sin introducir la inflación local del lado derecho,
    que es lo que arruinaría la regresión si se usara el TCR completo.
    """
    df = pd.concat({"tc": tc, "pe": precios_externos}, axis=1).dropna()
    if df.empty:
        raise ValueError("las series no se solapan en ninguna fecha")
    s = df["tc"] * df["pe"]
    s.name = "tc_deflactado_externo"
    return s
