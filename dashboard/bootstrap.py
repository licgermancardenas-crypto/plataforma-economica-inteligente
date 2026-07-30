"""
bootstrap — asegura que la base exista antes de renderizar el dashboard.
=======================================================================
En local la base ya está construida. En un deploy efímero (Streamlit Cloud) el
archivo no existe: este módulo corre init_db + ingest la primera vez, bajando los
datos de las APIs. Pensado para envolverse en st.cache_resource (una sola vez por
sesión de servidor).
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


def _necesita_build() -> bool:
    if not DB.exists():
        return True
    try:
        con = sqlite3.connect(DB)
        n = con.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        con.close()
        return n == 0
    except sqlite3.Error:
        return True


def ensure_data() -> str:
    """Construye la base si falta o está vacía. Devuelve la ruta a la DB."""
    if _necesita_build():
        import init_db
        import ingest
        init_db.main()
        ingest.main([])
    return str(DB)
