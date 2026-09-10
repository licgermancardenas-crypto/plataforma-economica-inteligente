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
  pass-through, VAR + impulso-respuesta, curva de Phillips, nowcasting de inflación con ML
  (ElasticNet, walk-forward) y **estabilidad de parámetros** (sup-Wald con bootstrap de
  regresores fijos, con su función de potencia). Reporte: `python3 scripts/analisis.py`.
  Hallazgos en [`docs/hallazgos_econometricos.md`](docs/hallazgos_econometricos.md).
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
  dossier antes de mostrarse. Cubre series, comparación entre gobiernos y los resultados
  econométricos (VAR con bandas, pass-through, nowcast) y el comercio espejo. Sin API key
  el dashboard funciona igual. Ver [`docs/capa_ia.md`](docs/capa_ia.md).
- ✅ **Etapa 9 — Comercio espejo (`platec/comercio_espejo.py`).** Panel bilateral de UN
  Comtrade (1992-2025, 208 declarantes) para medir la discrepancia entre lo que Argentina
  declara comerciar y lo que declara la contraparte: el insumo de la literatura de flujos
  financieros ilícitos por mala facturación. El ajuste CIF/FOB **se estima por país** en vez
  de imponer el 10% fijo de la literatura. Página propia en el dashboard. Ver
  [`docs/comercio_espejo.md`](docs/comercio_espejo.md).

## Estructura

```
platec/     núcleo analítico (data, stats, econometria, nowcast, insights, gobiernos,
            narrador, comercio_espejo, firmas_sinteticas)
dashboard/  app Streamlit (app.py) + bootstrap de datos
scripts/    utilidades ejecutables (validate_sources, init_db, ingest, snapshot, analisis)
sql/        DDL del esquema (schema.sql)
docs/       documentación técnica (fuentes validadas, hallazgos econométricos, capa de IA,
            comercio espejo) + notas/ (bitácora de investigación)
data/       snapshot.csv.gz (versionado) + plataforma.db (generada, ignorada)
```

## Uso

```bash
pip install -r requirements.txt          # o instalar a nivel usuario
python3 scripts/snapshot.py load         # base lista en ~1 s desde el snapshot del repo
streamlit run dashboard/app.py           # dashboard interactivo (http://localhost:8501)
python3 scripts/analisis.py              # reporte econométrico en consola
python3 -m pytest                        # suite de tests (235 casos)
```

Para reconstruir desde las fuentes en vez de usar el snapshot:

```bash
python3 scripts/init_db.py               # crea la base y siembra el catálogo
python3 scripts/ingest.py                # descarga el histórico de las 22 series
python3 scripts/ingest_comtrade.py       # panel de comercio espejo (anual, ~2 min)
python3 scripts/snapshot.py export       # congela el histórico para versionarlo
python3 scripts/snapshot.py export-espejo  # congela el panel espejo (aparte: es anual)
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

### Comercio espejo: la discrepancia no es flete
`platec/comercio_espejo.py` compara lo que Argentina declara exportar a cada socio contra lo
que ese socio declara importar de Argentina (y viceversa). Tres cosas que deciden si esa
comparación mide algo:

1. **El ajuste CIF/FOB no es un 10% fijo.** Es el supuesto estándar de la literatura y en el
   agregado no está mal —la mediana calculada sobre los datos da +7,5%—, pero por socio va de
   **+3,9% en Brasil a +12,5% en Australia**: es flete, y el flete es distancia. Aplicarle 10%
   a un vecino con frontera terrestre sobrecorrige seis puntos y **da vuelta el signo**. Acá
   el factor se estima por país declarante.
2. **`fobvalue = 0` no es un FOB de cero.** Comtrade devuelve cero —no `null`— para los países
   que no calculan esa valoración. China informa su importación de 2020 desde Argentina como
   CIF 6.814 millones y FOB 0. Tomar ese cero en serio llevaba la discrepancia del año a
   −27.000 millones: el 40% de las exportaciones argentinas, inventado por un cero.
3. **El signo no es el mismo en los dos canales.** Sacar divisas es declarar *de menos* al
   exportar y *de más* al importar. Cada canal lleva su orientación para que `gap > 0` sea
   salida en los dos; sumarlos sin eso mezcla peras con manzanas.

Lo que devuelve es una **discrepancia**, no una estimación de flujos ilícitos: el flete es la
única fuente de brecha lícita que los datos permiten corregir con precisión, y quedan afuera
las reexportaciones, los desfases de timing y la clasificación.

**El contraste contra la brecha cambiaria.** Si la discrepancia mide arbitraje, tiene que
crecer con el premio del arbitraje. En panel año × socio con efectos fijos, error agrupado
por año y p-valor por *wild cluster bootstrap* (con quince clusters el p asintótico daba
0,0008 contra 0,025 del bootstrap: treinta veces más chico), el resultado es **asimétrico**:

| Canal | β por punto de brecha | p |
|---|---|---|
| Exportador (subfacturar exportaciones) | **+0,059** | 0,025 |
| Importador (sobrefacturar importaciones) | +0,009 | 0,679 |

El canal exportador responde en las cuatro especificaciones —incluida la submuestra sin
ninguna imputación CIF/FOB, donde es más grande— y el importador es un cero limpio en todas.
Contra la lectura habitual de la prensa, que pone el foco en la sobrefacturación de
importaciones: **sobrefacturar exige acceso al dólar oficial, que es lo que el cepo raciona;
subfacturar exportaciones no exige permiso de nadie.** El control de cambios no elimina el
arbitraje, lo empuja hacia el lado que no controla. Detalle y límites en
[`docs/comercio_espejo.md`](docs/comercio_espejo.md).

### La hipótesis del riesgo país no se caía por falta de datos
El VAR diario `[riesgo país, TC, brecha]` arrancaba en 2013 porque lo limita el CCL. Sacando
la brecha se pierde una variable y se ganan **once años**: el bivariado `[riesgo país, TC]`
cubre **5.920 días desde marzo de 2002**, con el default, el canje de 2005 y la crisis de
2008 adentro. No arranca en 1999 aunque el riesgo país sí: durante la convertibilidad el peso
estaba fijo por ley y no hay tipo de cambio que modelar.

`Riesgo país → TC` **no es robusta en ninguno de los seis regímenes**. Si el canal existiera
en las crisis, once años más de muestra con tres crisis adentro deberían haberlo mostrado.
Lo que sí aguanta los seis rezagos, y en un solo régimen, es `TC → riesgo país` **en Cepo II**:
bajo cepo duro el tipo de cambio oficial es una *variable de política*, y moverlo informa
sobre la capacidad del gobierno de sostener el régimen — que es lo que el riesgo soberano pone
precio. Sin cepo, el TC absorbe esa información en simultáneo y no lidera.

**Y antes de mirar nada hubo que sacar un artefacto.** El EMBI+ cambia de valor cuando cambia
*qué mide*: al liquidarse un canje los bonos en default salen del índice. El 13/06/2005 el
riesgo país pasa de 6.606 a 794 puntos en una rueda y el 10/09/2020 de 2.120 a 1.101 — en log
son retornos de −212% y −65% que no son movimientos de precio. Un filtro de outliers no sirve:
el +52% del lunes post-PASO de 2019 es igual de extremo y es el dato más informativo de la
serie. Las fechas se listan a mano con su evento (`stats.RECOMPOSICIONES_EMBI`), como el tramo
INTERVENIDO del IPC.

> Eso **corrigió un resultado ya publicado**: el día del canje 2020 aportaba el 13% de la suma
> de cuadrados de los retornos en la muestra 2013-2026, y sin anularlo `TC → riesgo país` en
> Cepo II se leía frágil (4/6) cuando es robusta (6/6). El artefacto tapaba una relación real.

### «No se rechaza» no es lo mismo que «es estable»
El VAR mensual se estima **pooleado** sobre una muestra que cruza la crisis de 2018-19 y la
devaluación de dic-2023, mientras el VAR diario sí se parte por régimen. Esa asimetría se
resolvió testeando, no partiendo: con ~110 meses y once parámetros por ecuación, el corte de
dic-23 dejaría 30 observaciones de un lado y ahí no se estima nada.

El sup-Wald (fecha de quiebre desconocida, p-valor por bootstrap de regresores fijos à la
Hansen 2000) **no rechaza en ninguna de las cinco ecuaciones** — aunque el TC y el IPC ponen
los dos su máximo en **diciembre de 2023**, y la actividad y el riesgo país en **abril-mayo de
2020**: el test ubica los quiebres donde la historia dice que están, pero el estadístico no
llega.

Lo importante es lo que vino después. **Un "no se rechaza" sin función de potencia no dice
nada**, así que se midió por Monte Carlo qué podía detectar el test:

| Forma del quiebre | Tamaño | Potencia |
|---|---|---|
| Todas las pendientes | ×2,0 | **97%** |
| Salto de nivel | 2 desvíos del residuo | **97%** |
| Solo el pass-through (`tc_l1`) | 15 errores estándar | 12% |
| Solo el pass-through (`tc_l1`) | 30 errores estándar | 80% |

El sup-Wald prueba un quiebre en los once coeficientes a la vez: gasta todos los grados de
libertad del modelo para detectar un movimiento en uno. Conclusión honesta: **se descarta un
cambio de régimen generalizado, no se descarta un cambio en el pass-through** — que es justo
el parámetro del que dependen las IRF. Sus bandas siguen sin incorporar incertidumbre de
régimen, no por falta de test sino porque con 110 meses ese test no existe. Detalle en
[`docs/hallazgos_econometricos.md`](docs/hallazgos_econometricos.md) §7.

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

Sobre resultados econométricos la regla se endurece, porque **la estimación puntual sola no
es un resultado**: al dossier del VAR entran los dos límites del intervalo, su amplitud, en
cuántos horizontes excluye al cero y *la misma respuesta bajo cada ordenamiento de Cholesky
alternativo*. Recién con eso la prosa puede decir qué parte de la conclusión es evidencia y
qué parte es supuesto de identificación. Todo lo que la lectura natural querría restar
—la amplitud de una banda, la distancia entre el nowcast y el último dato oficial— viene
precalculado: si no, el modelo lo resta y el verificador lo marca como derivado, que es
correcto y a la vez inútil. Y lo que el proyecto no cree —el «p mínimo sobre 6 rezagos» de
la tabla de Granger, los coeficientes sin estandarizar del ElasticNet— directamente no
entra: un número que no creemos no se le da a un modelo cuya única defensa es no poder
afirmar de más.

El determinismo **no** viene de bajar la temperatura —los modelos actuales de la familia
Opus rechazan `temperature` con un 400— sino de cachear por hash del dossier: mismos datos,
mismo texto. Sin `ANTHROPIC_API_KEY` el módulo se aparta y el dashboard sigue mostrando el
panel de lectura automática determinístico. Detalle completo en
[`docs/capa_ia.md`](docs/capa_ia.md).

```bash
export ANTHROPIC_API_KEY="..."   # local; en Streamlit Cloud va como secret del deploy
```

### El único dato que la plataforma sí inventa, y cómo se lo aísla
`platec/firmas_sinteticas.py` genera estados contables de empresas **ficticias** con etiqueta
de verdad sobre qué maniobra ejecuta cada una — infraestructura de investigación, porque los
reportes de operación sospechosa son confidenciales por ley y no hay datos etiquetados
públicos.

Choca de frente con la regla que atraviesa el proyecto, así que se lo aísla por construcción:
**no persiste nada**. Se genera determinísticamente desde una semilla, así que la
reproducibilidad se consigue guardando un entero y ninguna fila sintética puede terminar al
lado de un dato real. Hay un test que verifica que el módulo no escribe en disco. En el
dashboard vive en una página aparte con el aviso arriba de todo.

Lo que lo hace no-trivial: **articulación contable**, **ley de Benford** (los montos salen de
una lognormal; con `uniform()` el problema se resuelve solo, porque la desviación de Benford
ya es un detector forense), **estructura sectorial real** del INDEC, **prevalencia baja** y
—lo que costó una versión entera— **la maniobra va a quien puede hacerla**: repartidas al
azar, la sobrefacturación quedaba diluida en firmas que apenas importaban y movía el margen
de 0,96 a 0,95.

**El puente con el macro.** La intensidad de la subfacturación se calibra para que la
discrepancia agregada reproduzca el β = +0,0589 estimado sobre datos reales. La
sobrefacturación **no** escala con la brecha, y eso es el hallazgo: β = +0,009 con p = 0,68,
porque exige acceso al dólar oficial que el cepo raciona.

Perseguir esa calibración destapó una implicancia: si se omite el 5,9% de las exportaciones y
ninguna firma omite más del 60% de las suyas, **al menos el 9,8% del valor exportado pasa por
manipuladores**. El umbral empírico coincide con el aritmético. Detalle en
[`docs/firmas_sinteticas.md`](docs/firmas_sinteticas.md).

> Un detector entrenado ahí encuentra las maniobras que uno mismo inyectó: sirve para comparar
> métodos y medir potencia, **no** como evidencia sobre la economía argentina.

### Bitácora de investigación
[`docs/notas/`](docs/notas/) es la capa que `docs/` no cubre: `docs/` documenta **lo que el
código hace**, las notas guardan **lo que se aprendió haciéndolo**. Cuatro archivos:
[literatura](docs/notas/literatura.md) (qué se tomó de cada método y qué no),
[decisiones descartadas](docs/notas/decisiones-descartadas.md) (con qué haría falta para darlas
vuelta), [trampas de datos](docs/notas/trampas-de-datos.md) (los errores silenciosos de las
fuentes) y [preguntas abiertas](docs/notas/preguntas-abiertas.md).

Se leen igual en GitHub y en Obsidian: son `.md` planos con links relativos estándar, sin
`[[wikilinks]]` ni plugins que generen contenido. Para abrirlas en Obsidian, `Open folder as
vault` sobre la raíz del repo — no hay nada que importar. `.obsidian/` está en el `.gitignore`.

### Datos: snapshot versionado
El histórico viaja en el repo como `data/snapshot.csv.gz` (~245 KB, 51k observaciones).
La base SQLite **no** se versiona: se reconstruye desde el snapshot en ~1 s, sin red.

Por qué: el contenedor de un deploy gratuito es efímero y se reinicia cada vez que la
app despierta. Reconstruir la base pegándole a BCRA/INDEC en cada arranque sumaba
decenas de segundos y, si una API rate-limiteaba o bloqueaba la IP del server, el
dashboard directamente no renderizaba. Ahora las APIs son una actualización opcional
(botón «Actualizar» en el sidebar y el workflow diario
[`refresh-data.yml`](.github/workflows/refresh-data.yml)), no un requisito para ver el
tablero. El panel de comercio espejo tiene su propio workflow
[`refresh-comercio-espejo.yml`](.github/workflows/refresh-comercio-espejo.yml), **mensual**
porque Comtrade publica una vez al año: correrlo a diario serían 68 llamadas para que no
cambie nada. Los snapshots se escriben con **gzip determinista**, así que el binario cambia
si y solo si cambiaron los datos. `snapshot.py export` se niega a congelar una base con series vacías, así que
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
