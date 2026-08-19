"""
bootstrap — asegura que la base exista Y esté COMPLETA antes de renderizar.
==========================================================================
En local la base ya está construida. En un deploy efímero (Streamlit Cloud) el
archivo no existe y el contenedor se reinicia cada vez que la app despierta.

Orden de preferencia, de barato a caro:
  1. La base ya está completa          -> no se hace nada.
  2. Hay snapshot versionado en el repo -> se carga desde disco, SIN red (~1 s).
  3. No hay snapshot                    -> ingesta desde las APIs (lento y frágil).

El punto 2 es lo que hace que el deploy sea utilizable: pegarle a BCRA/INDEC en
cada arranque agregaba decenas de segundos en el mejor caso, y en el peor —una
API caída, rate-limit, o la IP del server bloqueada— dejaba el dashboard sin
renderizar nada. Con el snapshot las APIs pasan a ser una actualización opcional
(`actualizar()`, botón en el sidebar), no un requisito para ver el tablero.

Robustez: la ingesta atrapa errores por serie y continúa, así que puede dejar la
base PARCIAL. Verificar solo COUNT>0 dejaría servido un dashboard incompleto en
silencio; acá se exige cobertura de TODAS las series activas y se completa lo
faltante desde el snapshot (idempotente) antes de dar el arranque por bueno.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "plataforma.db"

# Permite importar platec y los scripts de ingesta desde cualquier cwd
for p in (str(ROOT), str(ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import snapshot  # noqa: E402  (scripts/snapshot.py, ya en sys.path)


def _faltantes() -> list[str] | None:
    """
    Diagnóstico del estado de la base:
      - None  -> no existe o no tiene esquema  (requiere build completo)
      - []    -> completa: todas las series activas tienen observaciones
      - [ids] -> parcial: series activas sin ninguna observación
    """
    if not DB.exists():
        return None
    try:
        con = sqlite3.connect(DB)
        try:
            rows = con.execute(
                "SELECT s.series_id FROM series s "
                "LEFT JOIN observations o ON o.series_id = s.series_id "
                "WHERE s.active = 1 "
                "GROUP BY s.series_id HAVING COUNT(o.value) = 0"
            ).fetchall()
        finally:
            con.close()
        return [r[0] for r in rows]
    except sqlite3.Error:
        return None  # sin esquema todavía -> tratar como build completo


def _ingerir(series: list[str]) -> None:
    import ingest
    ingest.main(series)


def ensure_data() -> str:
    """
    Deja la base lista y garantiza que ninguna serie activa quede vacía.
    Devuelve la ruta a la DB. Lanza RuntimeError si el arranque queda incompleto
    (para que st.cache_resource no lo cachee y el reload reintente).
    """
    faltantes = _faltantes()
    if faltantes == []:
        return str(DB)

    if snapshot.existe():
        # Camino rápido del deploy: histórico congelado en el repo, sin red.
        snapshot.load(faltantes or None)
    elif faltantes is None:          # sin base ni snapshot -> catálogo + histórico completo
        import init_db
        init_db.main()
        _ingerir([])
    else:                            # parcial y sin snapshot -> reingerir lo que falta
        _ingerir(faltantes)

    faltantes = _faltantes()
    if faltantes:                    # sigue incompleto tras el intento
        raise RuntimeError(
            "Arranque incompleto; sin datos para: " f"{', '.join(faltantes)}. "
            "Si el repo trae data/snapshot.csv.gz el problema es de lectura del "
            "archivo; si no, fue rate-limit o caída de las APIs de origen "
            "(BCRA/INDEC). Recargá la página para reintentar.")
    return str(DB)


def estado_datos() -> dict:
    """
    Frescura de lo que se está mostrando, para exponerla en la UI.
    `ultima_obs` sale de la base real (no del snapshot) porque puede haber sido
    actualizada en caliente con `actualizar()`.
    """
    info = {"ultima_obs": None, "snapshot": snapshot.meta().get("generado")}
    try:
        con = sqlite3.connect(DB)
        try:
            info["ultima_obs"] = con.execute(
                "SELECT MAX(obs_date) FROM observations").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        pass
    return info


def actualizar(series: list[str] | None = None) -> tuple[bool, str]:
    """
    Actualización best-effort contra las APIs, disparada por el usuario.
    NUNCA propaga la excepción: si las fuentes no responden, el dashboard sigue
    en pie con los datos del snapshot. Devuelve (ok, mensaje para la UI).
    """
    antes = estado_datos()["ultima_obs"]
    try:
        _ingerir(series or [])
    except Exception as e:  # red caída, rate-limit, IP bloqueada, etc.
        return False, (f"No se pudo actualizar ({type(e).__name__}). "
                       f"Seguís viendo los datos al {antes}.")
    despues = estado_datos()["ultima_obs"]
    if despues and antes and despues > antes:
        return True, f"Datos actualizados: {antes} → {despues}."
    return True, f"Sin novedades en las fuentes; datos al {despues or antes}."
