# Plataforma Económica Inteligente

Sistema de monitoreo, análisis econométrico y explicación automática de indicadores
económicos de Argentina. Ver planificación completa en `Plataforma_Economica_Inteligente.pdf`.

**Foco:** seguimiento monetario-cambiario (expansión monetaria → presión cambiaria →
traslado a precios → actividad y empleo), con módulo de econometría aplicada.

## Estado

- ✅ **Etapa 1 — Fuentes de datos validadas.** 6 indicadores núcleo confirmados contra
  las APIs reales. Ver [`docs/fuentes_validadas.md`](docs/fuentes_validadas.md).
- ✅ **Etapa 2 — Esquema de almacenamiento.** Base SQLite con catálogo de 13 series y
  banderas de calidad. Esquema en [`sql/schema.sql`](sql/schema.sql); se crea con
  `python3 scripts/init_db.py`.
- ✅ **Etapa 3 — Pipeline de ingesta.** `scripts/ingest.py` puebla `observations`
  (41k+ obs, histórico completo de las 13 series) con normalización y banderas de calidad.
- ✅ **Etapa 4 — Núcleo analítico (`platec/`).** Acceso a datos como pandas, remuestreo a
  frecuencia común (`data.get_frame`) y estadísticos base (variaciones, medias móviles,
  z-score/outliers, deflactación) en `platec/stats.py`.
- ✅ **Etapa 6-7 — Módulo de econometría (`platec/econometria.py`, `platec/nowcast.py`).**
  Estacionariedad (ADF+KPSS), orden de integración, Granger, cointegración de Johansen,
  pass-through, VAR + impulso-respuesta, curva de Phillips y nowcasting de inflación con ML
  (ElasticNet, walk-forward). Reporte: `python3 scripts/analisis.py`. Hallazgos en
  [`docs/hallazgos_econometricos.md`](docs/hallazgos_econometricos.md).
- ⬜ Etapa 4-5 — Dashboard (Streamlit + Plotly).
- ⬜ Etapa 8 — Capa de IA (LLM vía API).

## Estructura

```
platec/     núcleo analítico (data.py, stats.py)
scripts/    utilidades ejecutables (validate_sources.py, init_db.py, ingest.py)
sql/        DDL del esquema (schema.sql)
docs/       documentación técnica (fuentes validadas)
data/       plataforma.db (SQLite) y data/raw/ (reportes, crudos)
```

## Uso

```bash
pip install -r requirements.txt          # o instalar a nivel usuario
python3 scripts/validate_sources.py      # revalidar acceso a las 5 fuentes
```

> Entorno: Python 3.13. Para aislar en venv hace falta `apt install python3.13-venv`
> (el sistema trae `venv` sin `ensurepip`).
