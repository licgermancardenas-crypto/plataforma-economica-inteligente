# Plataforma Económica Inteligente

Sistema de monitoreo, análisis econométrico y explicación automática de indicadores
económicos de Argentina. Ver planificación completa en `Plataforma_Economica_Inteligente.pdf`.

**Foco:** seguimiento monetario-cambiario (expansión monetaria → presión cambiaria →
traslado a precios → actividad y empleo), con módulo de econometría aplicada.

## Estado

- ✅ **Etapa 1 — Fuentes de datos validadas.** 6 indicadores núcleo confirmados contra
  las APIs reales. Ver [`docs/fuentes_validadas.md`](docs/fuentes_validadas.md).
- ✅ **Etapa 2 — Esquema de almacenamiento.** Base SQLite con catálogo de 22 series y
  banderas de calidad. Esquema en [`sql/schema.sql`](sql/schema.sql); se crea con
  `python3 scripts/init_db.py`.
- ✅ **Etapa 3 — Pipeline de ingesta.** `scripts/ingest.py` puebla `observations`
  (51k+ obs, histórico completo de las 22 series) con normalización y banderas de calidad.
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
- ✅ **Etapa 5b — Comparador de gobiernos (`platec/gobiernos.py`).** Periodización en
  nueve mandatos (1995→hoy) y comparación de indicadores entre ellos, normalizando por
  **PIB nominal** o pasando a USD para no comparar pesos de 2004 contra pesos de 2026.
  Ver [«Comparar gobiernos sin mentir»](#comparar-gobiernos-sin-mentir).
- ✅ **Etapa 8 — Capa de IA (`platec/narrador.py`).** Redacción automática de lecturas
  con LLM vía API, con **verificación numérica**: el modelo no calcula, recibe un dossier
  cerrado de hechos ya computados y cada número de su texto se contrasta contra ese
  dossier antes de mostrarse. Sin API key el dashboard funciona igual.
  Ver [`docs/capa_ia.md`](docs/capa_ia.md).

## Estructura

```
platec/     núcleo analítico (data, stats, econometria, nowcast, insights, gobiernos, narrador)
dashboard/  app Streamlit (app.py) + bootstrap de datos
scripts/    utilidades ejecutables (validate_sources, init_db, ingest, snapshot, analisis)
sql/        DDL del esquema (schema.sql)
docs/       documentación técnica (fuentes validadas, hallazgos econométricos, capa de IA)
data/       snapshot.csv.gz (versionado) + plataforma.db (generada, ignorada)
```

## Uso

```bash
pip install -r requirements.txt          # o instalar a nivel usuario
python3 scripts/snapshot.py load         # base lista en ~1 s desde el snapshot del repo
streamlit run dashboard/app.py           # dashboard interactivo (http://localhost:8501)
python3 scripts/analisis.py              # reporte econométrico en consola
python3 -m pytest                        # suite de tests (110 casos)
```

Para reconstruir desde las fuentes en vez de usar el snapshot:

```bash
python3 scripts/init_db.py               # crea la base y siembra el catálogo
python3 scripts/ingest.py                # descarga el histórico de las 22 series
python3 scripts/snapshot.py export       # congela el histórico para versionarlo
```

### Tests
`tests/` cubre los módulos de `platec/`: `stats` (transformaciones puras), `econometria`
y `nowcast` (validados contra series sintéticas de propiedades conocidas y contra la base
real), `data` (acceso y alineación de frecuencias), `insights` (lecturas automáticas) y
`gobiernos` (periodización, normalización por PBI y cobertura, con regresión anclada a las
magnitudes reales del PIB en dólares) y `narrador` (verificación numérica, caché y
reintentos, con el cliente del LLM inyectado como doble: ningún test toca la red ni
necesita credenciales). Los tests de integración se saltan solos si `data/plataforma.db`
no existe.

### Comparar gobiernos sin mentir
`platec/gobiernos.py` responde «¿cómo varió X en los últimos gobiernos?» esquivando las dos
trampas que arruinan esa comparación en Argentina:

1. **Nominal.** Comparar la base monetaria de 2004 contra la de 2026 en pesos es comparar
   inflación, no política monetaria. Todo lo que está en pesos se normaliza por **PIB nominal**
   (`pct_pib`) o se pasa a **USD** (`en_usd`). El PBI como denominador deja numerador y
   denominador en pesos del mismo trimestre: no interviene ningún índice de precios.
2. **Deflactar con un índice que no es creíble.** El IPC oficial 2007-2015 está marcado
   `INTERVENIDO` en `quality_periods` y `data.get_series` lo excluye por defecto. Usarlo como
   deflactor haría que ese tramo se viera artificialmente bien en términos reales.

Dos detalles que muerden:

- **El PIB trimestral del INDEC ya viene anualizado.** La serie se etiqueta «millones de pesos
  corrientes» con frecuencia trimestral, que se lee como «el PIB de ese trimestre». No lo es.
  Sumar los cuatro trimestres da 4,3x y hunde todos los ratios a un cuarto (la recaudación
  daría 5% del PBI en vez de 20%). Hay test de regresión anclado al control cruzado en dólares.
- **La cobertura se mide por tramo cubierto, no por conteo de observaciones.** Contar meses
  castiga a las series trimestrales por existir: le daría 0,33 al desempleo, que en realidad
  cubre entero cada mandato. Por debajo de `COBERTURA_MINIMA` (0,60) la tabla devuelve NaN en
  vez de un promedio de media docena de meses disfrazado de mandato.

Los nueve períodos agrupan la crisis 2001-2003 en un solo tramo: son cinco presidencias en
dieciocho meses y separarlas daría períodos de días, sin sentido estadístico.

### La capa de IA no puede inventar un número
`platec/narrador.py` redacta las lecturas con un LLM, pero el modelo **no calcula**: recibe
un `Dossier` cerrado —los hechos que ya computaron `insights`, `stats` y `gobiernos`, con
sus unidades y sus advertencias— y sólo escribe prosa sobre eso. Después, `verificar()`
extrae todos los números del texto y los contrasta contra el dossier. Se marcan como
huérfanos los inventados, los **reescalados** («45.511 millones» → «45,5 mil millones») y
los **derivados** (restar dos hechos autorizados para obtener un tercero): reescalar y
derivar son cuentas, y las cuentas son del lado de Python. Los años son la única excepción.

Si aparece un huérfano se reintenta señalándole al modelo *cuál* número está de más; si
insiste, la lectura se muestra marcada en vez de ocultarse.

El determinismo **no** viene de bajar la temperatura —los modelos actuales de la familia
Opus rechazan `temperature` con un 400— sino de cachear por hash del dossier: mismos datos,
mismo texto. Sin `ANTHROPIC_API_KEY` el módulo se aparta y el dashboard sigue mostrando el
panel de lectura automática determinístico. Detalle completo en
[`docs/capa_ia.md`](docs/capa_ia.md).

```bash
export ANTHROPIC_API_KEY="..."   # local; en Streamlit Cloud va como secret del deploy
```

### Datos: snapshot versionado
El histórico viaja en el repo como `data/snapshot.csv.gz` (~245 KB, 51k observaciones).
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
