"""Tests del arranque en frío (dashboard/bootstrap).

Protege el fix de arranque parcial: la base debe considerarse lista solo si
TODAS las series activas tienen observaciones, no apenas exista una fila.
Usa una copia temporal de la base real; se salta si esa base no existe.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
import bootstrap  # noqa: E402

pytestmark = pytest.mark.skipif(
    not bootstrap.DB.exists(), reason="requiere data/plataforma.db (correr init_db + ingest)"
)


@pytest.fixture
def db_temporal(tmp_path, monkeypatch):
    """Copia la base real a un temp y apunta bootstrap.DB ahí."""
    destino = tmp_path / "plataforma.db"
    shutil.copy(bootstrap.DB, destino)
    monkeypatch.setattr(bootstrap, "DB", destino)
    return destino


def test_base_completa_no_falta_nada(db_temporal):
    assert bootstrap._faltantes() == []


def test_arranque_parcial_detecta_series_vacias(db_temporal):
    con = sqlite3.connect(db_temporal)
    con.execute("DELETE FROM observations WHERE series_id IN ('reservas', 'usd_ccl')")
    con.commit()
    con.close()
    assert set(bootstrap._faltantes()) == {"reservas", "usd_ccl"}


def test_base_inexistente_pide_build_completo(db_temporal):
    db_temporal.unlink()
    assert bootstrap._faltantes() is None


def test_base_sin_esquema_pide_build_completo(db_temporal):
    # archivo que existe pero no es una base con esquema -> build completo
    db_temporal.write_bytes(b"no soy una base sqlite valida")
    assert bootstrap._faltantes() is None
