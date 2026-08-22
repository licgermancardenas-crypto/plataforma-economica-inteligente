"""
platec.data — acceso a la base como series pandas y alineación de frecuencias.
==============================================================================
Resuelve el problema de las FRECUENCIAS MIXTAS: cada serie vive en su frecuencia
nativa (D/M/Q) y esta capa la entrega ya indexada por fecha y, si se pide,
remuestreada a una frecuencia común para análisis multivariado (VAR, VECM, Granger).

Convención de fechas: obs_date es el primer día del período, por lo que se mapea
a los offsets 'MS' (month start) y 'QS' (quarter start) de pandas.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "plataforma.db"

# Frecuencia nativa (código en DB) -> offset de pandas
_FREQ_OFFSET = {"D": "D", "M": "MS", "Q": "QS"}
# Ranking de granularidad: menor = más fina
_FREQ_RANK = {"D": 0, "M": 1, "Q": 2}


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def metadata(series_id: str) -> dict:
    """Metadatos de una serie del catálogo."""
    with _connect() as con:
        row = con.execute("SELECT * FROM series WHERE series_id = ?", (series_id,)).fetchone()
    if row is None:
        raise KeyError(f"serie desconocida: {series_id}")
    return dict(row)


def catalogo() -> pd.DataFrame:
    """Catálogo completo de series como DataFrame."""
    with _connect() as con:
        return pd.read_sql("SELECT * FROM series ORDER BY indicator_id, series_id", con)


def indicadores() -> pd.DataFrame:
    """Catálogo de indicadores conceptuales como DataFrame."""
    with _connect() as con:
        return pd.read_sql("SELECT * FROM indicators ORDER BY indicator_id", con)


def get_series(series_id: str, start: str | None = None, end: str | None = None,
               exclude_flags: tuple[str, ...] = ("INTERVENIDO",)) -> pd.Series:
    """
    Devuelve la serie como pd.Series indexada por fecha (float), ordenada asc.
    Excluye por defecto las observaciones marcadas INTERVENIDO (calidad no confiable).
    `.attrs` lleva los metadatos (unit, frequency, kind, name, ...).
    """
    meta = metadata(series_id)
    q = ["SELECT obs_date, value FROM observations WHERE series_id = ?"]
    params: list = [series_id]
    if exclude_flags:
        q.append(f"AND quality_flag NOT IN ({','.join('?' * len(exclude_flags))})")
        params += list(exclude_flags)
    if start:
        q.append("AND obs_date >= ?"); params.append(start)
    if end:
        q.append("AND obs_date <= ?"); params.append(end)
    q.append("ORDER BY obs_date")
    with _connect() as con:
        rows = con.execute(" ".join(q), params).fetchall()
    idx = pd.to_datetime([r["obs_date"] for r in rows])
    s = pd.Series([r["value"] for r in rows], index=idx, name=series_id, dtype="float64")
    s.attrs.update(meta)
    return s


def _resample_una(s: pd.Series, freq_nativa: str, freq_obj: str, how: str) -> pd.Series:
    """Lleva una serie de su frecuencia nativa a la frecuencia objetivo."""
    if freq_nativa == freq_obj:
        return s
    offset = _FREQ_OFFSET[freq_obj]
    if _FREQ_RANK[freq_nativa] < _FREQ_RANK[freq_obj]:
        # nativa más fina que objetivo -> agregar (downsample)
        return getattr(s.resample(offset), how)()
    # nativa más gruesa que objetivo -> reindexar y arrastrar último valor (step)
    nuevo_idx = pd.date_range(s.index.min(), s.index.max(), freq=offset)
    return s.reindex(s.index.union(nuevo_idx)).ffill().reindex(nuevo_idx)


def get_frame(series_ids: list[str], freq: str = "M", how: str = "last",
              start: str | None = None, end: str | None = None,
              exclude_flags: tuple[str, ...] = ("INTERVENIDO",)) -> pd.DataFrame:
    """
    Varias series alineadas a una frecuencia común, listas para análisis multivariado.

    freq : 'D' | 'M' | 'Q'  (frecuencia objetivo)
    how  : 'last' (fin de período; apropiado para precios/stocks) |
           'mean' (promedio del período; apropiado para tasas/flujos)

    Las series más finas que `freq` se agregan con `how`; las más gruesas se
    arrastran (step / ffill). Devuelve un DataFrame con índice de fechas.
    """
    cols = {}
    for sid in series_ids:
        s = get_series(sid, start=start, end=end, exclude_flags=exclude_flags)
        cols[sid] = _resample_una(s, s.attrs["frequency"], freq, how)
    df = pd.concat(cols, axis=1)
    df.columns = series_ids
    return df
