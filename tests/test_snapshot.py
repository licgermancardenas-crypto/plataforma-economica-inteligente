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
    # También el espejo: sin aislarlo, cualquier test que exporte pisaría el
    # snapshot versionado del repo con lo que tenga la base del temp.
    monkeypatch.setattr(snapshot, "SNAPSHOT_ESPEJO", tmp_path / "snapshot_espejo.csv.gz")
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


# ---------------------------------------------------------------------------
# Comercio espejo
# ---------------------------------------------------------------------------
def _mirror(db: Path) -> set:
    con = sqlite3.connect(db)
    try:
        return set(con.execute(
            "SELECT year, reporter_code, partner_code, flow_code, primary_value, "
            "fob_value, cif_value FROM trade_mirror"))
    finally:
        con.close()


def test_roundtrip_del_espejo_conserva_las_filas(entorno):
    original = _mirror(entorno)
    if not original:
        pytest.skip("la base no tiene comercio espejo ingerido")
    snapshot.export()            # `load` reconstruye desde los dos archivos
    snapshot.export_espejo()
    entorno.unlink()
    snapshot.load()
    assert _mirror(entorno) == original


def test_el_cero_de_comtrade_sobrevive_al_roundtrip_como_cero():
    """
    `fobvalue = 0` es un valor que Comtrade manda de verdad. El snapshot tiene que
    devolverlo como 0.0 y no como None: el filtro de ese cero es de LECTURA, y la
    base guarda lo que dijo la fuente.
    """
    con = sqlite3.connect(":memory:")
    con.executescript((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
    con.execute("INSERT INTO trade_mirror (year, reporter_code, partner_code, "
                "flow_code, primary_value, fob_value, cif_value) VALUES (?,?,?,?,?,?,?)",
                (2020, 156, 32, "M", 6814456938.0, 0.0, 6814456938.0))
    fila = con.execute("SELECT fob_value, cif_value FROM trade_mirror").fetchone()
    assert fila[0] == 0.0 and fila[1] == 6814456938.0


def test_el_export_del_espejo_se_niega_a_encoger(entorno):
    """
    Guardrail del workflow mensual, que escribe sin nadie mirando. La ingesta no
    borra y la base se reconstruye desde el snapshot antes de actualizar, así que
    un snapshot que encoge significa base incompleta, no menos comercio.
    """
    if not _mirror(entorno):
        pytest.skip("la base no tiene comercio espejo ingerido")
    snapshot.export_espejo()
    completo = snapshot._filas_congeladas()
    assert completo > 1

    con = sqlite3.connect(entorno)
    con.execute("DELETE FROM trade_mirror WHERE year > (SELECT MIN(year) FROM trade_mirror)")
    con.commit(); con.close()

    with pytest.raises(SystemExit, match="encogería"):
        snapshot.export_espejo()
    assert snapshot._filas_congeladas() == completo, "el snapshot bueno quedó intacto"


def test_el_export_del_espejo_encoge_si_se_fuerza(entorno):
    if not _mirror(entorno):
        pytest.skip("la base no tiene comercio espejo ingerido")
    snapshot.export_espejo()
    completo = snapshot._filas_congeladas()
    con = sqlite3.connect(entorno)
    con.execute("DELETE FROM trade_mirror WHERE year > (SELECT MIN(year) FROM trade_mirror)")
    con.commit(); con.close()

    snapshot.export_espejo(force=True)
    assert snapshot._filas_congeladas() < completo


def test_sin_snapshot_espejo_el_load_no_falla(entorno):
    """El espejo es opcional: una base sin él tiene que cargar igual."""
    snapshot.SNAPSHOT_ESPEJO.unlink(missing_ok=True)
    assert snapshot.load_espejo() == 0


def test_el_gzip_es_determinista(entorno):
    """
    Mismo contenido, mismos bytes. Por defecto gzip escribe la hora de creación en la
    cabecera, así que dos exports de la MISMA base daban binarios distintos. Eso
    rompe el `git diff --quiet` con el que los workflows deciden si hay algo nuevo:
    el mensual commitearía 217 KB todos los meses aunque no cambiara un reporte.
    """
    import time
    snapshot.export()
    primero = snapshot.SNAPSHOT.read_bytes()
    time.sleep(1.1)                       # que cambie el reloj entre los dos exports
    snapshot.export()
    assert snapshot.SNAPSHOT.read_bytes() == primero


def test_el_gzip_del_espejo_tambien_es_determinista(entorno):
    import time
    if not _mirror(entorno):
        pytest.skip("la base no tiene comercio espejo ingerido")
    snapshot.export_espejo()
    primero = snapshot.SNAPSHOT_ESPEJO.read_bytes()
    time.sleep(1.1)
    snapshot.export_espejo()
    assert snapshot.SNAPSHOT_ESPEJO.read_bytes() == primero


def test_la_cabecera_gzip_no_lleva_ni_hora_ni_nombre(entorno):
    """Los bytes 4-7 son el mtime; el bit 3 del flag indica nombre incrustado."""
    snapshot.export()
    cab = snapshot.SNAPSHOT.read_bytes()[:8]
    assert cab[:2] == b"\x1f\x8b", "no es un gzip"
    assert cab[4:8] == b"\x00\x00\x00\x00", "la cabecera sigue llevando la hora"
    assert not cab[3] & 0x08, "la cabecera sigue llevando el nombre del archivo"
