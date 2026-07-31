"""
platec.insights — lectura automática de series (sin LLM).
=========================================================
Funciones puras sobre pd.Series que extraen observaciones cuantitativas
interpretables: posición en el rango histórico, racha, momentum, aceleración
y detección de anomalías. Alimentan los paneles de "insights" del dashboard
y, más adelante, la capa de IA (que las redacta, no las calcula).

Cada insight es un dict {texto, tono} donde `tono` ∈
{'alza', 'baja', 'alerta', 'neutro'} para el coloreado en la UI.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import stats

_PERIODOS_ANUALES = {"D": 252, "M": 12, "Q": 4}
_ETIQUETA_PERIODO = {"D": "días", "M": "meses", "Q": "trimestres"}


def _limpia(s: pd.Series) -> pd.Series:
    return s.dropna()


def posicion_historica(s: pd.Series) -> float:
    """Percentil (0-100) del último valor dentro de toda la muestra."""
    s = _limpia(s)
    if s.empty:
        return float("nan")
    return float((s <= s.iloc[-1]).mean() * 100)


def racha(s: pd.Series) -> int:
    """
    Períodos consecutivos con la misma dirección de cambio.
    Positivo = sube; negativo = baja; 0 = sin racha (último cambio nulo).
    """
    d = _limpia(s).diff().dropna()
    if d.empty:
        return 0
    signo = np.sign(d.iloc[-1])
    if signo == 0:
        return 0
    n = 0
    for v in d.values[::-1]:
        if np.sign(v) == signo:
            n += 1
        else:
            break
    return int(n * signo)


def momentum(s: pd.Series, corta: int = 3, larga: int = 12) -> float:
    """
    Momentum: cuánto se despega la media móvil corta de la larga, en % de la larga.
    Positivo = el nivel reciente acelera por encima de su promedio de mediano plazo.
    """
    s = _limpia(s)
    if len(s) < larga:
        return float("nan")
    mc = s.tail(corta).mean()
    ml = s.tail(larga).mean()
    if ml == 0:
        return float("nan")
    return float((mc / ml - 1) * 100)


def es_anomalia(s: pd.Series, umbral: float = 2.5, ventana: int = 24) -> bool:
    """El último valor es un outlier (|z-score rolling| > umbral) respecto de su ventana."""
    s = _limpia(s)
    if len(s) <= ventana:
        return False
    z = stats.zscore(s, ventana=ventana).iloc[-1]
    return bool(pd.notna(z) and abs(z) > umbral)


def insights_serie(s: pd.Series, es_tasa: bool = False,
                   nombre: str = "la serie") -> list[dict]:
    """
    Genera una lista de insights legibles a partir de una serie ya indexada.
    `es_tasa`: si es una tasa/porcentaje (desempleo, TNA) para redactar en pp.
    Cada elemento: {"texto": str, "tono": str}.
    """
    s = _limpia(s)
    out: list[dict] = []
    if len(s) < 3:
        return out

    freq = s.attrs.get("frequency", "M")
    unidad_periodo = _ETIQUETA_PERIODO.get(freq, "períodos")

    # 1) Posición en el rango histórico
    pct = posicion_historica(s)
    if pct >= 90:
        out.append({"texto": f"En el percentil {pct:.0f} de su historia: "
                             "cerca de **máximos**.", "tono": "alza"})
    elif pct <= 10:
        out.append({"texto": f"En el percentil {pct:.0f} de su historia: "
                             "cerca de **mínimos**.", "tono": "baja"})
    else:
        out.append({"texto": f"En el percentil {pct:.0f} de su rango histórico.",
                    "tono": "neutro"})

    # 2) Racha
    r = racha(s)
    if abs(r) >= 3:
        direccion = "en alza" if r > 0 else "a la baja"
        tono = "alza" if r > 0 else "baja"
        out.append({"texto": f"**{abs(r)} {unidad_periodo}** consecutivos {direccion}.",
                    "tono": tono})

    # 3) Momentum (mediano plazo) — solo para frecuencias con muestra suficiente
    m = momentum(s)
    if pd.notna(m) and abs(m) >= 2:
        signo = "acelera al alza" if m > 0 else "se desacelera"
        tono = "alza" if m > 0 else "baja"
        out.append({"texto": f"El nivel reciente {signo} "
                             f"({m:+.1f}% vs. su promedio de mediano plazo).",
                    "tono": tono})

    # 4) Anomalía en el último dato
    if es_anomalia(s):
        out.append({"texto": "El último dato es **atípico** frente a su "
                             "comportamiento reciente (posible quiebre o dato provisorio).",
                    "tono": "alerta"})

    return out
