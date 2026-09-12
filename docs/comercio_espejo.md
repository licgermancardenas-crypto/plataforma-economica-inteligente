# Comercio espejo — medir la discrepancia sin confundirla con flete

**Módulos:** `platec/comercio_espejo.py`, `scripts/ingest_comtrade.py` ·
**Tests:** `tests/test_comercio_espejo.py` · **Fuente:** UN Comtrade

Este documento explica una medición, no una funcionalidad. La pregunta es cuánta divisa
sale de Argentina por mala facturación comercial —subfacturar exportaciones, sobrefacturar
importaciones—, y la respuesta ingenua a esa pregunta está mal por construcción.

---

## 1. La idea y su trampa

Cada operación de comercio exterior se declara **dos veces**: una en la aduana argentina y
otra en la del socio. En un mundo sin errores ni maniobras las dos cifras coinciden. La
diferencia entre lo que Argentina declara exportar a Brasil y lo que Brasil declara importar
de Argentina es la **discrepancia espejo**.

La trampa: **la mayor parte de esa discrepancia es lícita.**

| Fuente de discrepancia | ¿Se corrige acá? |
|---|---|
| Flete y seguro (CIF contra FOB) | **Sí**, y es lo único que los datos permiten corregir con precisión |
| Reexportaciones vía terceros países | No |
| Desfase de timing en el cruce de aduana | No |
| Clasificación distinta de los dos lados | No |
| País de origen contra país de procedencia | No |

Por eso lo que devuelve el módulo se llama **discrepancia**, no «flujos ilícitos». Es un
límite superior ruidoso, no una estimación.

## 2. El ajuste CIF/FOB no es un 10% fijo

La literatura estándar (GFI y buena parte de la que la sigue) aplica un factor fijo de
~10% para pasar el CIF del importador a FOB. Medido contra los datos, ese supuesto es
razonable **en el agregado** y equivocado **país por país**:

| Socio | Factor CIF/FOB estimado |
|---|---|
| Brasil | +3,9% |
| Estados Unidos | +4,5% |
| Uruguay | +5,8% |
| Bolivia | +7,2% |
| Paraguay | +8,0% |
| Chile | +9,6% |
| Australia | +12,5% |
| **Mediana global (calculada)** | **+7,5%** |

Es flete, y el flete es distancia: los vecinos con frontera terrestre están en un dígito
bajo y Australia al otro lado del mundo, en dos dígitos. Aplicarle 10% a Brasil
**sobrecorrige seis puntos y puede dar vuelta el signo** de la discrepancia, convirtiendo
una subfacturación en un superávit espejo que no existe. Hay un test que fija exactamente
ese contrafáctico.

Acá el factor se **estima por país declarante**, con la mediana de los años en que ese país
informa las dos valoraciones, y solo se cae a la mediana global —también calculada, no
supuesta— cuando nunca informa ambas. La jerarquía es:

1. El **FOB que informó el propio declarante**. Comtrade lo trae en el mismo registro para
   una parte de los países; Argentina es uno de ellos incluso en importaciones, así que el
   canal importador no necesita estimar nada del lado argentino.
2. Su CIF deflactado por **su** factor.
3. Su CIF deflactado por la **mediana global**.

El origen viaja con el número (`origen_ar`, `origen_socio`) porque un FOB reportado y uno
imputado no valen lo mismo, y `cobertura_fob` dice qué fracción del **valor** —no del
conteo de países— salió de un reporte real.

> **Un factor absurdo es un error de reporte, no un flete.** En los datos de 2022 hay un
> registro con un cociente CIF/FOB de 9.993%. El flete de un embarque no es cien veces su
> valor. Sin acotar el factor a `[1,0 ; 1,5]`, un solo registro basura corre la mediana de
> un país entero.

## 3. El cero que no es un dato

El error más caro de todo el módulo, y el que justifica leer los datos antes de creerles:

**Comtrade devuelve `fobvalue = 0` —cero, no `null`— para los países que no calculan esa
valoración.** China informa su importación desde Argentina de 2020 como
`cif = 6.814 millones`, `fob = 0`.

Tomar ese cero como un FOB legítimo hace que el socio «declare» cero contra una exportación
argentina real. Con ese bug, la discrepancia del canal exportador daba **−27.000 millones
de dólares en 2020**: el 40% de las exportaciones argentinas, inventado por un cero. En un
solo año hay 83 registros así, tapando 35 mil millones de dólares de valor.

Un cero no es un dato faltante en ningún lado salvo acá, así que `_valor()` lo filtra
explícitamente en vez de confiar en `notna`. El snapshot guarda el cero **tal cual llega**:
el filtro es de lectura, no de ingesta, para que la base siga siendo lo que dijo la fuente.

## 4. El signo no es el mismo en los dos canales

Confundirlos suma peras con manzanas en el agregado. La maniobra que saca divisas es
declarar **de menos** al exportar y **de más** al importar:

| Canal | Salida de divisas cuando… | `gap` |
|---|---|---|
| exportador | el socio dice haber recibido **más** de lo que Argentina declara haber mandado | `socio − argentina` |
| importador | Argentina dice haber pagado **más** de lo que el socio declara haber mandado | `argentina − socio` |

Con esa orientación, **`gap > 0` significa salida de divisas en los dos**. Un test fija
cada signo por separado; el bug estaba en la primera versión y lo encontró el test, no la
lectura del código.

## 5. Qué dan los datos (1992-2025)

19.607 filas, 208 declarantes. Discrepancia total, promedio anual en millones de dólares:

| Período | Promedio | Régimen cambiario |
|---|---|---|
| 2003-2011 | 1.294 | — |
| 2012-2015 | 5.349 | Cepo I |
| 2016-2019 | 3.720 | Sin cepo |
| 2020-2023 | 5.831 | Cepo II |

Las magnitudes son 2-8% del comercio total, el rango que reporta la literatura para
Argentina, y el patrón por régimen apunta en la dirección esperada: más discrepancia con
cepo que sin cepo.

> Las magnitudes son plausibles y el patrón apunta donde se espera, pero una tabla mirada
> a ojo no es un resultado. El contraste está en la sección siguiente.

## 6. El contraste: ¿la discrepancia responde al precio del arbitraje?

Si la discrepancia mide mala facturación motivada por el arbitraje cambiario, tiene que
crecer con la **brecha**: cuando comprar al oficial y vender al paralelo deja 80%,
subfacturar una exportación paga ese 80%. Sin brecha no hay premio y la maniobra no tiene
sentido económico. Es el test que separa una medida contable de un hallazgo: si la
discrepancia no se mueve con el precio del arbitraje, probablemente esté midiendo flete,
timing y reexportaciones.

### Por qué en panel y no en serie de tiempo

La brecha existe en la base desde 2011: **quince observaciones anuales**. Una regresión de
series de tiempo con n=15 no distingue casi nada. El panel año × socio da ~1.000
observaciones por canal y permite absorber con efectos fijos todo lo propio de cada socio
—incluido el error del factor CIF/FOB imputado, que para un mismo país es constante en el
tiempo—.

Pero **el panel no multiplica los grados de libertad**: la brecha es común a todos los
socios de un año, así que la información que identifica el coeficiente sigue siendo la de
quince años. Por eso el error se agrupa por año y no por socio, y por eso hace falta lo
que sigue.

### Wild cluster bootstrap, y qué pasa si no se hace

Con quince clusters la varianza cluster-robusta asintótica está sesgada a la baja. Medido
acá: el p asintótico del canal exportador da **0,0008** y el del bootstrap **0,025** —
**treinta veces más grande**. Reportar el primero sería vender como decisivo un resultado
que es sugerente. Se usa el bootstrap de Cameron, Gelbach y Miller (2008): pesos Rademacher
por cluster, hipótesis nula impuesta.

### Resultado

`gap_pct[socio,t] = α_socio + β · brecha[t] + ε`, efectos fijos por socio, error agrupado
por año, p por bootstrap (1.999 réplicas). β se lee como puntos porcentuales de discrepancia
—sobre el comercio de ese par— por cada punto de brecha.

| Especificación | β exportador | p | β importador | p |
|---|---|---|---|---|
| Principal (brecha blue) | **+0,0589** (0,018) | 0,025 | +0,0086 (0,019) | 0,679 |
| Brecha CCL | +0,0470 (0,019) | 0,060 | +0,0025 (0,021) | 0,898 |
| Sin 2020 (COVID) | +0,0547 (0,018) | 0,038 | +0,0120 (0,020) | 0,556 |
| Sin ninguna imputación CIF/FOB | +0,0751 (0,027) | 0,051 | +0,0028 (0,021) | 0,882 |

**El canal exportador responde; el importador no.** El coeficiente exportador se sostiene en
las cuatro especificaciones —incluida la submuestra donde ambos lados reportan su FOB y no
interviene ningún factor imputado, donde de hecho es más grande— y el importador es un cero
limpio en todas.

Magnitud: β = 0,059 implica que pasar de brecha cero a brecha 100% agrega ~5,9 puntos
porcentuales de discrepancia sobre las exportaciones. Sobre exportaciones de ~70 mil
millones de dólares, del orden de **4 mil millones al año**.

### La asimetría es el hallazgo

La lectura habitual en la prensa argentina pone el foco en la **sobrefacturación de
importaciones**. Los datos dicen lo contrario: ese canal no responde a la brecha, y el
exportador sí. Tiene una explicación económica directa y verificable contra la historia
institucional: **sobrefacturar una importación exige acceso al dólar oficial**, que es
justamente lo que el cepo raciona vía DJAI, SIMI o SIRA. **Subfacturar una exportación no
exige permiso de nadie**: alcanza con dejar la diferencia afuera. El canal que escala con
el premio del arbitraje es el que no necesita la autorización del Estado.

Dicho de otro modo: el control de cambios no elimina el arbitraje, lo empuja hacia el lado
que no controla.

### Qué NO prueba esto

- **No hay identificación causal.** Es una asociación en quince años con efectos fijos de
  socio. Los años de brecha alta en Argentina son también años de crisis, controles y
  recesión: cualquiera de esas cosas puede mover la discrepancia por su cuenta.
- **Sigue siendo una discrepancia.** Las reexportaciones vía terceros países, los desfases
  de timing y la clasificación distinta no se corrigen y podrían correlacionar con el ciclo.
- **Quince clusters son pocos** incluso con bootstrap. Los p entre 0,03 y 0,06 son
  sugerentes, no concluyentes.
- **La cobertura FOB no es el confusor**, y eso sí está chequeado: su correlación con la
  brecha es **0,007**. El resultado no viene de que cambie qué países reportan.

```python
ce.contraste_brecha("exportador")                      # principal
ce.contraste_brecha("exportador", solo_reportado=True) # sin ninguna imputación
ce.contraste_brecha("importador", excluir_anios=(2020,))
```

## 7. La fuente y sus límites

`scripts/ingest_comtrade.py` usa el endpoint **público y gratuito** de Comtrade
(`/public/v1/preview`), sin credenciales. No usa el paquete `comtradeapicall`: sus funciones
que agregan valor (`getBilateralData`, `getFinalData`) exigen subscription key de pago, y
lo que queda es este mismo REST en treinta líneas. Sumar una dependencia al build por eso
no se paga; los otros tres fetchers del proyecto están escritos igual.

Límites medidos contra la API real (2026-09):

- **Un período por llamada.** `period=2015,2016` devuelve 400.
- **Techo de 500 registros por respuesta.** Argentina contra todos los socios, un año, ambos
  flujos, da ~350: entra con poco aire. Si alguna vez se baja a capítulo HS esto explota. El
  ingestor **falla en vez de truncar callado**: un agregado calculado sobre un subconjunto
  arbitrario de socios sería peor que un error.
- **Rezago de ~1 año.** A septiembre de 2026 hay datos hasta 2025, pero 2025 tiene 183 filas
  de socios contra ~280 de un año cerrado: muchos todavía no reportaron. Los últimos dos
  años son provisorios por composición, no por revisión.

**Cadencia.** Comtrade es anual y se publica una vez al año. Por eso el panel viaja en
`data/snapshot_espejo.csv.gz`, **aparte** de `snapshot.csv.gz`: ese lo reescribe y lo
commitea el workflow todos los días, y meter acá un binario de comercio exterior lo haría
cambiar a diario sin que cambiara un dato. `snapshot.py load` carga los dos.

Lo mantiene al día [`refresh-comercio-espejo.yml`](../.github/workflows/refresh-comercio-espejo.yml),
**mensual** (día 8, 16:00 UTC). Reingiere solo los **últimos tres años**: el histórico viejo
no se mueve y lo que cambia entre corridas es que un socio que faltaba completó su año. Son
seis llamadas. El modo manual (`workflow_dispatch`) acepta un año inicial para rehacer todo.

Dos cosas que hacen falta para que eso funcione sin nadie mirando:

- **El gzip es determinista** (`mtime=0`, sin nombre incrustado). Por defecto gzip escribe
  la hora de creación en la cabecera, así que dos exports de la misma base dan binarios
  distintos y el `git diff --quiet` con el que el job decide si hay algo nuevo daría siempre
  que sí: 217 KB commiteados todos los meses aunque no cambie un reporte.
- **`export-espejo` se niega a encoger.** La ingesta no borra y la base se reconstruye desde
  el snapshot antes de actualizar, así que un snapshot con menos filas que el versionado
  significa base incompleta, no menos comercio. Es el mismo criterio por el que `export`
  aborta con una serie vacía.

El job diario y el mensual escriben archivos distintos pero sobre la misma rama, así que el
mensual rebasa antes de pushear y reintenta hasta tres veces.

## 8. Por qué una tabla y no series

`observations` es `(series_id, obs_date)`: una serie de tiempo univariada. El comercio
espejo es un **panel de cuatro dimensiones** (año × quién declara × contraparte × flujo).
Meterlo en `series` obligaría a inventar cientos de `series_id` sintéticos y, sobre todo,
haría inexpresable el apareo espejo, que es la operación por la que existe la tabla.

Se guarda **crudo**, tal como lo reporta cada país. La discrepancia, el ajuste CIF/FOB y la
agregación se derivan en pandas — mismo criterio que el saldo comercial y el remuestreo:
las transformaciones no se persisten.

```bash
python3 scripts/init_db.py
python3 scripts/ingest_comtrade.py 1992 2025   # ~2 min, 68 llamadas
python3 scripts/snapshot.py export-espejo
```

En el dashboard tiene página propia (**🌐 Comercio espejo**): la serie anual por canal con
los períodos de cepo sombreados, el factor CIF/FOB por socio contra el 10% de la literatura,
el diagrama de dispersión contra la brecha con la pendiente estimada, y el detalle por socio
declarando si cada FOB es reportado o imputado.

**Los años provisorios se marcan y no encabezan.** Un año cuyos socios apareados caen por
debajo del 85% de la mediana del canal se marca `provisorio`; el titular de la página se
ancla al último año **completo**. En 2025 se aparean 51 socios contra ~70 de un año cerrado
y el agregado cambia de signo: falta comercio declarado, no hay menos comercio. En el
gráfico esos años van rayados además de aclarados, porque la textura sobrevive al blanco y
negro y al daltonismo y la opacidad no.

```python
from platec import comercio_espejo as ce
ce.factores_cif_fob()          # factor por país declarante
ce.discrepancia(desde=2015)    # panel año × socio × canal
ce.por_anio(desde=2015)        # agregado con cobertura_fob
ce.serie_anual("exportador")   # serie con índice de fechas
```

---

## Dónde sigue esto

- **La brecha** contra la que se contrasta la discrepancia sale del análisis cambiario de
  [hallazgos econométricos](hallazgos_econometricos.md).
- **El β estimado acá calibra** el generador de [firmas sintéticas](firmas_sinteticas.md): la
  misma maniobra, vista a nivel firma en vez de agregado.
- **La literatura**, con qué se tomó de GFI y qué no —el factor CIF/FOB fijo del 10% no—:
  [literatura](notas/literatura.md).
- **El `fobvalue = 0`** de Comtrade y su clase de error:
  [trampas de datos](notas/trampas-de-datos.md).
- **Lo que falta para tener contrafáctico** (el modelo de gravedad):
  [preguntas abiertas](notas/preguntas-abiertas.md).
