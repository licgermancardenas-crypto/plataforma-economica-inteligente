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
- ✅ **Etapa 4-5 — Dashboard (`dashboard/app.py`, Streamlit + Plotly).** Cockpit de
  indicadores, detalle por indicador con gráficos y tablas exportables, y panel de
  econometría. Corre local con `streamlit run dashboard/app.py`.
- ⬜ Etapa 8 — Capa de IA (LLM vía API).

## Estructura

```
platec/     núcleo analítico (data, stats, econometria, nowcast)
dashboard/  app Streamlit (app.py) + bootstrap de datos
scripts/    utilidades ejecutables (validate_sources, init_db, ingest, analisis)
sql/        DDL del esquema (schema.sql)
docs/       documentación técnica (fuentes validadas, hallazgos econométricos)
data/       plataforma.db (SQLite) y data/raw/ (reportes, crudos)
```

## Uso

```bash
pip install -r requirements.txt          # o instalar a nivel usuario
python3 scripts/init_db.py               # crea la base y siembra el catálogo
python3 scripts/ingest.py                # descarga el histórico de las 13 series
python3 scripts/analisis.py              # reporte econométrico en consola
streamlit run dashboard/app.py           # dashboard interactivo (http://localhost:8501)
python3 -m pytest                        # suite de tests (30 casos, ~20s)
```

### Tests
`tests/` cubre los cuatro módulos de `platec/`: `stats` (transformaciones puras),
`econometria` y `nowcast` (validados contra series sintéticas de propiedades conocidas
y contra la base real), y `data` (acceso e alineación de frecuencias). Los tests de
integración se saltan solos si `data/plataforma.db` no existe.

### Deploy (Streamlit Community Cloud)
1. En [share.streamlit.io](https://share.streamlit.io) conectar este repo.
2. Main file path: `dashboard/app.py`.
3. La primera carga corre `init_db` + `ingest` automáticamente (`dashboard/bootstrap.py`),
   así que la base **no** se versiona: se reconstruye desde las APIs en el server.

> Entorno: Python 3.13. Para aislar en venv hace falta `apt install python3.13-venv`
> (el sistema trae `venv` sin `ensurepip`).
