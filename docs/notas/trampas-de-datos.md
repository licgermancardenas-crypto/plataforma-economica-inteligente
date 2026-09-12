# Trampas de datos

Errores silenciosos de las fuentes: los que no tiran excepción, no dejan un hueco visible y
producen un número plausible que está mal. Cada uno de estos costó horas y ninguno se habría
encontrado leyendo la documentación de la fuente.

Todos tienen test de regresión. La nota existe para que el test tenga una explicación y para
no volver a caer en la misma clase de error con una fuente nueva.

---

## El PIB trimestral del INDEC ya viene anualizado

**Serie:** `pib_corriente` · **Test:** `tests/test_gobiernos.py`

La serie se etiqueta «millones de pesos corrientes» con frecuencia trimestral, lo que se lee
como «el PIB de ese trimestre». **No lo es.** Sumar los cuatro trimestres da 4,3× el PIB real
y hunde todos los ratios a un cuarto: la recaudación daría 5% del PBI en vez de 20%.

El control cruzado que lo detectó fue pasar a dólares y comparar contra el PIB conocido de
Argentina. Hay test de regresión anclado a esa magnitud.

**La clase de error:** una etiqueta de unidad que es literalmente correcta y semánticamente
engañosa. Ante cualquier serie de flujo trimestral nueva, cruzar contra una magnitud conocida
antes de usarla como denominador.

---

## Comtrade devuelve `fobvalue = 0`, no `null`

**Módulo:** [`comercio_espejo.md`](../comercio_espejo.md) §3 · **Test:** `tests/test_comercio_espejo.py`

Los países que no calculan la valoración FOB la reportan como **cero**, no como faltante.
China informa su importación desde Argentina de 2020 como `cif = 6.814 millones`, `fob = 0`.

Tomar ese cero como un FOB legítimo hace que el socio «declare» cero contra una exportación
argentina real. Con ese bug la discrepancia del canal exportador daba **−27.000 millones de
dólares en 2020**: el 40% de las exportaciones argentinas, inventado por un cero. En un solo
año hay 83 registros así, tapando 35 mil millones de valor.

**Lo que lo delató:** el número era absurdo. Si hubiera sido −2.000 millones en vez de
−27.000, habría pasado.

**La clase de error:** cero como centinela de faltante. `notna()` no alcanza; hay que filtrar
por valor. Se filtra **al leer**, no al ingerir: la base guarda lo que dijo la fuente.

---

## El EMBI+ cambia de valor porque cambia de definición

**Módulo:** `platec/stats.py` (`RECOMPOSICIONES_EMBI`) · **Test:** `tests/test_stats.py`

Al liquidarse un canje de deuda, los bonos en default salen del índice y entran los nuevos.
El 13/06/2005 el riesgo país pasa de **6.606 a 794** puntos básicos en una rueda; el
10/09/2020, de **2.120 a 1.101**. En log-diferencias son retornos de −212% y −65% que no son
movimientos de precio: el índice mide otra cosa a partir de ese día.

**Por qué un filtro de outliers no sirve.** El 12/08/2019, el lunes posterior a las PASO, el
riesgo país salta **+52%**. Es tan extremo estadísticamente como una recomposición y es el
dato más informativo de la serie. Cualquier regla por z-score borraría los dos. Las fechas se
listan a mano con el evento que las justifica.

**Qué se rompe:** la variación, no el nivel. Y devuelve NaN, no cero — un cero afirmaría que
no hubo movimiento.

**Lo que costó:** el día del canje 2020 aportaba el 13% de la suma de cuadrados de los
retornos en la muestra 2013-2026, y su presencia hacía leer como frágil (4/6) una relación que
es robusta (6/6). Tapaba un resultado real.

**La clase de error:** un índice que se redefine sin cambiar de nombre. Aplica a cualquier
serie con recomposiciones, rebases o empalmes — y la defensa no es estadística sino
documental.

---

## El menos tipográfico U+2212 no es el guion ASCII

**Módulo:** [`capa_ia.md`](../capa_ia.md) · **Test:** `tests/test_narrador.py`

Un modelo que escribe con tipografía correcta usa `−` (U+2212), no `-`. El verificador
numérico parseaba con un regex que solo contemplaba el ASCII, así que **«−0,80» se leía como
+0,80** y toda IRF negativa legítima salía marcada como número inventado.

Estaba latente desde el principio: ya afectaba a `dossier_serie` en cualquier variación
interanual negativa.

Se normaliza **solo** el menos matemático. La raya `–` (U+2013) queda afuera a propósito:
separa rangos («2017–2026») y convertirla en signo inventaría un «-2026».

**La clase de error:** un carácter Unicode que *se ve* como otro. Aparece en cualquier
parseo de texto generado por un modelo.

---

## gzip escribe la hora en la cabecera

**Módulo:** `scripts/snapshot.py` · **Test:** `tests/test_snapshot.py`

Dos exports de la **misma** base daban binarios distintos: gzip guarda la hora de creación y
el nombre del archivo original en la cabecera. Contenido descomprimido idéntico (mismo md5),
bytes 4-7 distintos.

Eso rompía la premisa del workflow mensual: `git diff --quiet` habría dado siempre que sí y
el job habría commiteado 217 KB todos los meses aunque no cambiara un reporte — exactamente
la churn que la cadencia mensual busca evitar.

Se escribe con `mtime=0` y sin nombre incrustado.

**La clase de error:** metadata no determinista en un artefacto que se versiona. Aplica a
cualquier formato comprimido o empaquetado.

---

## El IPC oficial 2007-2015 está intervenido

**Módulo:** `platec/data.py`, tabla `quality_periods`

No es un error de parseo sino de credibilidad, y por eso está en la base como bandera y no en
el código como excepción: `data.get_series` excluye `INTERVENIDO` por defecto.

La trampa práctica es usarlo **como deflactor**: haría que ese tramo se viera artificialmente
bien en términos reales, sin que aparezca ningún hueco ni ningún error.

**La clase de error:** dato presente, sintácticamente impecable, no confiable. La única
defensa es una bandera de calidad de primera clase en el esquema.

---

## `apis.datos.gob.ar` corta por timeout de forma intermitente

**Módulo:** `scripts/ingest.py`

No es silencioso —falla visiblemente— pero es **parcial**: una corrida puede traer cuatro de
las siete series y las otras tres fallan. El 2026-08-26 hicieron falta cuatro corridas para
completar.

La ingesta es incremental y no borra, así que reintentar es seguro. Pero hay que **mirar la
salida** y reintentar hasta que no queden `✗`, y `snapshot.py export` se niega a congelar una
base con series vacías justamente por esto.

---

## El preview de Comtrade tiene techo de 500 registros

**Módulo:** `scripts/ingest_comtrade.py`

Argentina contra todos los socios, un año, ambos flujos, da ~350: entra, pero con poco aire.
Si alguna vez se baja a nivel de capítulo HS, explota.

El ingestor **falla en vez de truncar callado**: un agregado calculado sobre un subconjunto
arbitrario de socios sería peor que un error, porque nadie lo notaría.

**La clase de error:** paginación implícita. Una API que devuelve «los primeros N» sin decir
que hay más.

---

# Trampas propias

Las de arriba las pone la fuente. Estas nos las pusimos nosotros, y son peores: una fuente
ajena no tiene por qué avisar, pero un artefacto propio se puede evitar.

## Un generador puede regalarle la respuesta al detector

**Módulo:** `platec/firmas_sinteticas.py` · **Test:** `tests/test_deteccion.py`

El detector sobre el panel sintético dio **PR-AUC 0,89 con prevalencia 2%**. Para un problema
de AML eso es demasiado bueno para ser cierto, y lo era. Dos fugas, las dos en el generador:

1. **Soportes disjuntos.** La intensidad exportadora de las firmas limpias se sorteaba en
   [0,00 – 0,35] y la de las subfacturadoras en [0,45 – 0,85]. Cero solapamiento: la regla
   `exportador > 0,40` las identificaba perfecto. El clasificador aprendía a reconocer **el
   sorteo**, no la maniobra.
2. **Variación nula entre ejercicios.** La intensidad comercial era idéntica todos los años,
   así que su desvío era **exactamente cero** para toda firma limpia y se volvía el mejor
   predictor del panel.

Corregido —las limpias también comercian, las manipuladoras salen de esa misma población, y
hay ruido año a año— el PR-AUC bajó a 0,785.

**Lo que lo delató:** que el número fuera bueno. No hubo excepción, no hubo NaN, no hubo nada
raro en los datos. Sólo un resultado demasiado lindo.

**La clase de error:** en datos sintéticos, cualquier parámetro sorteado de distribuciones
distintas según la etiqueta es una fuga potencial. La defensa que quedó es un test que falla
si una sola característica se lleva más del 95% de la importancia, y la regla de lectura:
**un detector que anda demasiado bien es un diagnóstico sobre el dataset, no un logro.**

## Una anomalía que salta a la vista no mide ningún detector

**Módulo:** `platec/firmas_sinteticas.py`

La primera calibración de la tipología «entidad reactivada» producía saltos de facturación de
hasta **400 veces**. Es detectable a ojo, y por eso inútil: un dataset donde la anomalía se ve
sola no discrimina entre métodos.

Lo mismo, en la otra dirección, con la sobrefacturación de importaciones antes de asignarla a
firmas importadoras: movía el margen de 0,96 a 0,95 y **no significaba nada**.

**La clase de error:** un caso de prueba mal calibrado —demasiado obvio o demasiado sutil—
no es un caso de prueba. El rango útil es el que obliga a mirar.
