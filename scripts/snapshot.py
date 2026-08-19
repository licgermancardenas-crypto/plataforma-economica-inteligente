#!/usr/bin/env python3
"""
snapshot — congela las observaciones en un archivo versionable.
===============================================================
Motivo: en un deploy efímero (Streamlit Community Cloud) el contenedor arranca
sin `data/plataforma.db` y se reinicia cada vez que la app despierta. Reconstruir
la base pegándole a BCRA/INDEC en cada arranque es lento y frágil: basta que una
API rate-limitee, tarde o bloquee la IP del server (el caso típico con BCRA desde
afuera de Argentina) para que el dashboard no renderice NADA.

Solución: el histórico viaja en el repo como CSV comprimido (~41k obs, cientos de
KB) y el arranque lo carga en SQLite sin tocar la red. Las APIs pasan a ser una
ACTUALIZACIÓN opcional, no un requisito para ver el tablero.

El snapshot guarda solo `observations`: el catálogo (series, indicadores, reglas
de calidad) es código y lo siembra `init_db.py`.

Uso:
    python3 scripts/snapshot.py export      # DB -> data/snapshot.csv.gz  (tras ingerir)
    python3 scripts/snapshot.py load        # snapshot -> DB (init_db + carga, sin red)
    python3 scripts/snapshot.py info        # qué hay congelado y de cuándo
"""
from __future__ import annotations

import csv
import gzip
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "plataforma.db"
SNAPSHOT = ROOT / "data" / "snapshot.csv.gz"
META = ROOT / "data" / "snapshot_meta.json"

COLUMNAS = ("series_id", "obs_date", "value", "quality_flag")


def _corto(p: Path) -> str:
    """Ruta relativa al repo si se puede (en tests apunta a un temp)."""
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def _cobertura(con) -> dict[str, dict]:
    """Por serie activa: cantidad de observaciones y rango de fechas."""
    filas = con.execute(
        "SELECT s.series_id, COUNT(o.value), MIN(o.obs_date), MAX(o.obs_date) "
        "FROM series s LEFT JOIN observations o ON o.series_id = s.series_id "
        "WHERE s.active = 1 GROUP BY s.series_id ORDER BY s.series_id").fetchall()
    return {sid: {"obs": n, "desde": desde, "hasta": hasta}
            for sid, n, desde, hasta in filas}


def export(force: bool = False) -> Path:
    """
    Vuelca `observations` a data/snapshot.csv.gz + metadata.

    Guardrail: se niega a congelar una base incompleta (alguna serie activa sin
    datos). Un snapshot parcial se propaga al deploy y deja el dashboard mutilado
    en silencio, que es justo lo que se quiere evitar.
    """
    if not DB_PATH.exists():
        raise SystemExit(f"no existe {DB_PATH}: correr init_db.py + ingest.py primero")
    con = sqlite3.connect(DB_PATH)
    try:
        cobertura = _cobertura(con)
        vacias = [sid for sid, c in cobertura.items() if c["obs"] == 0]
        if vacias and not force:
            raise SystemExit(
                "base incompleta, sin datos para: " + ", ".join(vacias) +
                "\nCorré `python3 scripts/ingest.py " + " ".join(vacias) + "` "
                "o forzá con --force si es intencional.")

        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        filas = con.execute(
            "SELECT series_id, obs_date, value, quality_flag FROM observations "
            "ORDER BY series_id, obs_date")
        n = 0
        with gzip.open(SNAPSHOT, "wt", newline="", encoding="utf-8", compresslevel=9) as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNAS)
            for fila in filas:
                w.writerow(fila)
                n += 1
    finally:
        con.close()

    META.write_text(json.dumps({
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observaciones": n,
        "ultima_obs": max((c["hasta"] for c in cobertura.values() if c["hasta"]), default=None),
        "series": cobertura,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"snapshot: {n} obs -> {_corto(SNAPSHOT)} "
          f"({SNAPSHOT.stat().st_size / 1024:.0f} KB)")
    return SNAPSHOT


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def existe() -> bool:
    return SNAPSHOT.exists()


def meta() -> dict:
    """Metadata del snapshot congelado ({} si no hay)."""
    if not META.exists():
        return {}
    try:
        return json.loads(META.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load(series: list[str] | None = None) -> int:
    """
    Crea/completa la base desde el snapshot, SIN red. Devuelve obs cargadas.
    `series` limita la carga a esas series (para completar una base parcial).
    """
    if not SNAPSHOT.exists():
        raise FileNotFoundError(f"no hay snapshot en {SNAPSHOT}")

    sys.path.insert(0, str(ROOT / "scripts"))
    import init_db
    init_db.main()  # idempotente: esquema + catálogo

    filtro = set(series) if series else None
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        with gzip.open(SNAPSHOT, "rt", newline="", encoding="utf-8") as fh:
            r = csv.reader(fh)
            cab = next(r, None)
            if tuple(cab or ()) != COLUMNAS:
                raise ValueError(f"snapshot con cabecera inesperada: {cab}")
            lote, n = [], 0
            for sid, fecha, valor, flag in r:
                if filtro is not None and sid not in filtro:
                    continue
                lote.append((sid, fecha, float(valor), flag))
                if len(lote) >= 5000:
                    con.executemany(
                        "INSERT OR REPLACE INTO observations "
                        "(series_id, obs_date, value, quality_flag) VALUES (?,?,?,?)", lote)
                    n += len(lote)
                    lote = []
            if lote:
                con.executemany(
                    "INSERT OR REPLACE INTO observations "
                    "(series_id, obs_date, value, quality_flag) VALUES (?,?,?,?)", lote)
                n += len(lote)
        con.commit()
    finally:
        con.close()
    return n


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "info"
    if cmd == "export":
        export(force="--force" in argv)
    elif cmd == "load":
        print(f"cargadas {load()} obs en {_corto(DB_PATH)}")
    elif cmd == "info":
        m = meta()
        if not m:
            print("no hay snapshot congelado (correr: snapshot.py export)")
            return
        print(f"generado   : {m['generado']}")
        print(f"últ. obs   : {m['ultima_obs']}")
        print(f"observac.  : {m['observaciones']}")
        for sid, c in m.get("series", {}).items():
            print(f"  {sid:16} {c['obs']:6} obs  [{c['desde']}..{c['hasta']}]")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
