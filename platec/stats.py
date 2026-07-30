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
