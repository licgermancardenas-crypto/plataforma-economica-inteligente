"""Tests del snapshot versionado (scripts/snapshot.py + arranque del dashboard).

Lo que protegen:
  1. Round-trip: exportar y volver a cargar reproduce las observaciones exactas.
  2. Guardrail: nunca congelar una base incompleta (un snapshot parcial se
     propagaría al deploy y mutilaría el dashboard en silencio).
  3. Arranque en frío sin red: sin base pero con snapshot, ensure_data() la deja
     completa sin llamar a la ingesta.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "scripts"))
import bootstrap  # noqa: E402
import snapshot  # noqa: E402

pytestmark = pytest.mark.skipif(
    not bootstrap.DB.exists(), reason="requiere data/plataforma.db (correr init_db + ingest)"
)


def _obs(db: Path) -> set:
    con = sqlite3.connect(db)
    try:
        return set(con.execute(
            "SELECT series_id, obs_date, value, quality_flag FROM observations"))
    finally:
        con.close()


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Aísla DB y snapshot en un temp, partiendo de la base real."""
    import shutil
    db = tmp_path / "plataforma.db"
    shutil.copy(bootstrap.DB, db)
    for mod in (snapshot, bootstrap):
        monkeypatch.setattr(mod, "DB_PATH" if mod is snapshot else "DB", db)
    monkeypatch.setattr(snapshot, "SNAPSHOT", tmp_path / "snapshot.csv.gz")
    monkeypatch.setattr(snapshot, "META", tmp_path / "snapshot_meta.json")
    # init_db escribe en su propia constante de módulo
    import init_db
    monkeypatch.setattr(init_db, "DB_PATH", db)
    return db


def test_roundtrip_conserva_las_observaciones(entorno, capsys):
    original = _obs(entorno)
    snapshot.export()
    entorno.unlink()
    n = snapshot.load()
    assert n == len(original)
    assert _obs(entorno) == original


def test_export_rechaza_base_incompleta(entorno):
    con = sqlite3.connect(entorno)
    con.execute("DELETE FROM observations WHERE series_id = 'reservas'")
    con.commit()
    con.close()
    with pytest.raises(SystemExit, match="reservas"):
        snapshot.export()
    assert not snapshot.SNAPSHOT.exists()


def test_meta_reporta_ultima_observacion(entorno):
    snapshot.export()
    m = snapshot.meta()
    con = sqlite3.connect(entorno)
    esperado = con.execute("SELECT MAX(obs_date) FROM observations").fetchone()[0]
    con.close()
    assert m["ultima_obs"] == esperado
    assert m["observaciones"] > 0


def test_arranque_en_frio_usa_el_snapshot_sin_red(entorno, monkeypatch, capsys):
    snapshot.export()
    entorno.unlink()

    def _sin_red(series):
        raise AssertionError("ensure_data no debe pegarle a las APIs si hay snapshot")

    monkeypatch.setattr(bootstrap, "_ingerir", _sin_red)
    bootstrap.ensure_data()
    assert bootstrap._faltantes() == []


def test_arranque_parcial_se_completa_desde_el_snapshot(entorno, monkeypatch):
    snapshot.export()
    con = sqlite3.connect(entorno)
    con.execute("DELETE FROM observations WHERE series_id IN ('reservas', 'usd_ccl')")
    con.commit()
    con.close()
    monkeypatch.setattr(bootstrap, "_ingerir",
                        lambda series: (_ for _ in ()).throw(AssertionError("sin red")))
    bootstrap.ensure_data()
    assert bootstrap._faltantes() == []
