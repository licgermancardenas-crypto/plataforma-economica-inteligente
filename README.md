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
platec/     núcleo analítico (data, stats, econometria, nowcast, insights)
dashboard/  app Streamlit (app.py) + bootstrap de datos
scripts/    utilidades ejecutables (validate_sources, init_db, ingest, snapshot, analisis)
sql/        DDL del esquema (schema.sql)
docs/       documentación técnica (fuentes validadas, hallazgos econométricos)
data/       snapshot.csv.gz (versionado) + plataforma.db (generada, ignorada)
```

## Uso

```bash
pip install -r requirements.txt          # o instalar a nivel usuario
python3 scripts/snapshot.py load         # base lista en ~1 s desde el snapshot del repo
streamlit run dashboard/app.py           # dashboard interactivo (http://localhost:8501)
python3 scripts/analisis.py              # reporte econométrico en consola
python3 -m pytest                        # suite de tests (50 casos)
```

Para reconstruir desde las fuentes en vez de usar el snapshot:

```bash
python3 scripts/init_db.py               # crea la base y siembra el catálogo
python3 scripts/ingest.py                # descarga el histórico de las 13 series
python3 scripts/snapshot.py export       # congela el histórico para versionarlo
```

### Tests
`tests/` cubre los cuatro módulos de `platec/`: `stats` (transformaciones puras),
`econometria` y `nowcast` (validados contra series sintéticas de propiedades conocidas
y contra la base real), y `data` (acceso e alineación de frecuencias). Los tests de
integración se saltan solos si `data/plataforma.db` no existe.

### Datos: snapshot versionado
El histórico viaja en el repo como `data/snapshot.csv.gz` (~190 KB, 41k observaciones).
La base SQLite **no** se versiona: se reconstruye desde el snapshot en ~1 s, sin red.

Por qué: el contenedor de un deploy gratuito es efímero y se reinicia cada vez que la
app despierta. Reconstruir la base pegándole a BCRA/INDEC en cada arranque sumaba
decenas de segundos y, si una API rate-limiteaba o bloqueaba la IP del server, el
dashboard directamente no renderizaba. Ahora las APIs son una actualización opcional
(botón «Actualizar» en el sidebar y el workflow diario
[`refresh-data.yml`](.github/workflows/refresh-data.yml)), no un requisito para ver el
tablero. `snapshot.py export` se niega a congelar una base con series vacías, así que
un snapshot parcial nunca llega al deploy.

### Dónde corre (y dónde no)
Streamlit es un **servidor de larga vida**: mantiene un WebSocket abierto con el navegador
y reejecuta el script en cada interacción. Eso descarta las plataformas serverless de
sitios estáticos — **Vercel, Netlify o GitHub Pages no pueden servirlo** (responden 404:
no hay build estático que publicar, y sus funciones mueren a los segundos). Sirven, en
cambio, Streamlit Community Cloud, Hugging Face Spaces, Render, Railway o Fly.io.

### Deploy (Streamlit Community Cloud)
1. En [share.streamlit.io](https://share.streamlit.io) conectar este repo.
2. Main file path: `dashboard/app.py`.
3. Nada más: el arranque lee el snapshot del repo. Tiempos medidos en frío (sin base):
   cockpit ~2 s, explorador ~0,1 s, econometría ~3,5 s.

> El primer despliegue igual tarda unos minutos **una vez**, instalando las dependencias
> (statsmodels, scikit-learn, scipy). Eso es del builder de Streamlit, no de la app.

> Entorno: Python 3.13. Para aislar en venv hace falta `apt install python3.13-venv`
> (el sistema trae `venv` sin `ensurepip`).
