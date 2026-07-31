"""
bootstrap — asegura que la base exista Y esté COMPLETA antes de renderizar.
==========================================================================
En local la base ya está construida. En un deploy efímero (Streamlit Cloud) el
archivo no existe: este módulo corre init_db + ingest la primera vez, bajando los
datos de las APIs. Pensado para envolverse en st.cache_resource (una sola vez por
sesión de servidor).

Robustez del arranque en frío: la ingesta atrapa errores por serie y continúa,
así que un rate-limit/caída transitoria de una API puede dejar la base PARCIAL
(algunas series sin datos). Verificar solo COUNT>0 dejaría servido un dashboard
incompleto en silencio. En cambio, acá se exige cobertura de TODAS las series
activas: si falta alguna se reintenta solo lo faltante (la ingesta es idempotente)
y, si aun así queda incompleta, se lanza un error claro para que el reload reintente.
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


def ensure_data() -> str:
    """
    Construye/completa la base y garantiza que ninguna serie activa quede vacía.
    Devuelve la ruta a la DB. Lanza RuntimeError si el arranque queda incompleto
    (para que st.cache_resource no lo cachee y el reload reintente).
    """
    faltantes = _faltantes()
    if faltantes is None:            # sin base/esquema -> catálogo + histórico completo
        import init_db
        import ingest
        init_db.main()
        ingest.main([])
    elif faltantes:                  # parcial -> reingerir solo lo que falta
        import ingest
        ingest.main(faltantes)

    faltantes = _faltantes()
    if faltantes:                    # sigue incompleto tras el intento
        raise RuntimeError(
            "Ingesta incompleta en el arranque; sin datos para: "
            f"{', '.join(faltantes)}. Suele ser rate-limit o caída transitoria de "
            "las APIs de origen (BCRA/INDEC). Recargá la página para reintentar."
        )
    return str(DB)
