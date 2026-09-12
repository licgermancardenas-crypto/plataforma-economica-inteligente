# Literatura

Los métodos que sostienen cada decisión del proyecto, con **qué se tomó de cada uno y qué
no**. No es una bibliografía: es el registro de por qué el código hace lo que hace.

---

## Inferencia con pocos clusters

**Cameron, Gelbach & Miller (2008), «Bootstrap-based improvements for inference with
clustered errors»** · *Review of Economics and Statistics* 90(3)

De acá sale el *wild cluster bootstrap* con pesos Rademacher e hipótesis nula impuesta que
usa [`comercio_espejo.md`](../comercio_espejo.md) §6.

**Qué resolvió:** con quince clusters (años), la varianza cluster-robusta asintótica está
sesgada a la baja. Medido en este proyecto: el p asintótico del canal exportador daba
**0,0008** y el del bootstrap **0,025**, treinta veces más grande. Reportar el primero habría
vendido como decisivo un resultado que es sugerente.

**Lo que sigue sin resolver:** quince clusters son pocos *incluso* con bootstrap. La
corrección mejora la calibración, no crea información.

---

## Tests de quiebre con fecha desconocida

**Andrews (1993), «Tests for parameter instability and structural change with unknown change
point»** · *Econometrica* 61(4)
**Hansen (2000), «Testing for structural change in conditional models»** · *Journal of
Econometrics* 97(1)
**Davies (1977)** — el problema del parámetro no identificado bajo la nula

Sostienen la §7 de [`hallazgos_econometricos.md`](../hallazgos_econometricos.md).

**De Andrews se toma el estadístico** (sup-Wald sobre las fechas candidatas del tramo
central) y **no las tablas de valores críticos**, que suponen homocedasticidad.

**De Hansen se toma el bootstrap de regresores fijos**: regenerar la dependiente como el
residuo por un normal estándar manteniendo los regresores. Da p-valores válidos bajo
heterocedasticidad y sin exigir regresores estacionarios.

**De Davies, el motivo de fondo para no usar Chow:** bajo la nula la fecha de quiebre no está
identificada, así que el máximo sobre fechas no tiene la distribución del estadístico en una
fecha fija. Elegir la fecha mirando los datos y después usar una chi-cuadrado es hacer trampa.

**Lo que la literatura no da y hubo que construir:** la **función de potencia**. Ningún paper
dice qué puede detectar el test *en esta muestra*, y sin eso «no se rechaza» no distingue
entre no haber quiebre y no poder verlo. Se midió por Monte Carlo y el resultado cambió la
conclusión: el sup-Wald ve un cambio de régimen generalizado (potencia 97%) y es ciego a un
cambio en un coeficiente aislado (12% con quince errores estándar).

---

## Bandas de la impulso-respuesta

**Runkle (1987)** · **Lütkepohl (2005), cap. 3.7** — bootstrap de residuos para IRF

Se implementó a mano en `platec/econometria.py` en vez de usar statsmodels, **por un bug**:
`VARResults.irf_resim` (el motor de `errband_mc`) devuelve en la versión instalada las N
réplicas idénticas entre sí —desvío entre réplicas ~1e-15— así que las bandas colapsan sobre
el estimador puntual. Un intervalo de ancho cero no es un error visible: es un gráfico que
miente con cara de rigor.

**Limitación asumida:** es un intervalo percentil simple, sin corrección de sesgo. En muestras
cortas tiende a quedar angosto. Es un piso de la incertidumbre, no un techo, y así está
declarado en el dossier que lee el LLM.

---

## Mala facturación comercial y flujos financieros ilícitos

**Global Financial Integrity — [Mirror Analysis Methodology](https://gfintegrity.org/reports/methodology/trade-misinvoicing-mirror-analysis/)**
Código en [gfintegrity/Trade_Misinvoicing-DOTS](https://github.com/gfintegrity/Trade_Misinvoicing-DOTS) (R, GPL-3, sin tocar desde 2019)

**Lépissier, Davis & Ibrahim (2021), «Presenting a new atlas of illicit financial flows from
trade misinvoicing»** · [SSRN 3984323](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3984323)

**UNU-WIDER WP 2022/24, «Measuring illicit financial flows: a gravity model approach»** ·
[PDF](https://www.wider.unu.edu/sites/default/files/Publications/Working-paper/PDF/wp2022-24-measuring-illicit-financial-flows-gravity-model-international-trade-misinvoicing.pdf)

**De GFI se toma la construcción del apareo espejo** y el tratamiento de reexportaciones.
**No se toma su factor CIF/FOB fijo del 10%**: medido sobre los datos, va de +3,9% en Brasil a
+12,5% en Australia. Es flete, y el flete es distancia. Aplicarle 10% a un vecino con frontera
terrestre sobrecorrige seis puntos y da vuelta el signo de la discrepancia. La mediana global
*calculada* da +7,5%, lo que valida el supuesto en el agregado y lo invalida país por país.

**De Lépissier y de UNU-WIDER se toma la crítica al supuesto ingenuo** —que toda discrepancia
espejo es misinvoicing— y la idea de un contrafáctico por modelo de gravedad. **El modelo de
gravedad no está implementado**: ver [preguntas abiertas](preguntas-abiertas.md).

---

## Fuga de capitales en Argentina

**«La fuga de capitales en la Argentina reciente (1976-2018)»** ·
[Redalyc](https://www.redalyc.org/journal/909/90958481002/html/)

Aporta el encuadre histórico: la subfacturación de exportaciones y la sobrefacturación de
importaciones como mecanismos clásicos, y la observación de que **los métodos basados en el
mercado cambiario oficial capturan solo la porción lícita**.

**Contra la lectura habitual:** la prensa pone el foco en la sobrefacturación de
importaciones. El contraste contra la brecha da lo contrario — ese canal no responde y el
exportador sí. La explicación institucional es que sobrefacturar exige acceso al dólar
oficial, que es lo que el cepo raciona vía DJAI, SIMI o SIRA; subfacturar exportaciones no
exige permiso de nadie.

---

## Tipologías de lavado y sus indicadores

**FATF/Egmont (2021), «Trade-Based Money Laundering: Risk Indicators»** ·
[PDF](https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/Trade-Based-Money-Laundering-Risk-Indicators.pdf)
**FATF/Egmont (2020), «TBML: Trends and Developments»** ·
[PDF](https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/Trade-Based-Money-Laundering-Trends-and-Developments.pdf)

Es el documento operativo del área. **35 indicadores en cuatro categorías**: estructurales
(12), de actividad comercial (7), de documentos y mercadería (8), y de cuenta y transacciones
(8).

**Qué se tomó:** tres tipologías de `firmas_sinteticas` salen textualmente de ahí —
*«purchases clearly exceed the economic capabilities of the entity»*, *«newly formed or
recently re-activated trade entity engages in high-volume activity»*, *«unexplained periods of
dormancy»*— y dos más que ya existían quedaron ancladas a sus indicadores. Cada tipología cita
su fuente en `TIPOLOGIAS[...].fuente`, con test que verifica que ninguna exista sin respaldo.

**Qué NO se puede tomar, y es el hallazgo:** contados contra lo que un balance anual contiene,
**sólo unos siete de los 35 son observables**. El 80% son de documentos aduaneros y de
movimientos de cuenta. Eso convierte «el estado contable es un mal lugar para detectar lavado»
en un número, y es la razón de fondo por la que la fortaleza de esta plataforma sigue siendo
la medición macro y no la detección a nivel firma.

**GAFILAT — Recopilación de tipologías regionales 2009-2016** ·
[PDF vía MPF](https://www.mpf.gob.ar/procelac-lavado/files/2020/04/GAFILAT.2009-2016RecopilacionTipologias.pdf)
**GAFILAT — Informe de tipologías regionales 2019-2020** ·
[PDF](https://biblioteca.gafilat.org/wp-content/uploads/2024/04/Informe-de-Tipologias-Regionales-de-LA-2019-2020-GAFILAT.pdf)

El organismo regional del que Argentina es miembro. De acá sale la confirmación de que
**pantalla y fachada son categorías separadas** en la taxonomía oficial, no una sutileza:
la sección V (vehículos corporativos) le dedica seis entradas propias a la fachada (§54, §64,
§65, §69 entre otras). El generador sólo modelaba la pantalla, que es la variante fácil.

**UIF Argentina — Tipologías, tendencias y amenazas** ·
[página](https://www.argentina.gob.ar/uif/internacional/tipolog%C3%ADas-tendencias-amenazas)

Casos argentinos, incluido uno de lavado vía operaciones comerciales e inmobiliarias con
sociedades pantalla. El sitio bloquea la descarga automática (403): hay que bajar los PDF a
mano.

---

## Métricas bajo desbalance extremo

**Saito & Rehmsmeier (2015), «The precision-recall plot is more informative than the ROC plot
when evaluating binary classifiers on imbalanced datasets»** · *PLOS ONE* 10(3)

Sostiene la elección de métricas de `platec/deteccion.py`.

**Qué se tomó:** PR-AUC como métrica principal, con el piso de azar en la **prevalencia** y no
en 0,5. Y ROC-AUC reportado pero con la advertencia puesta: se apoya en la tasa de falsos
positivos, y con 98% de negativos esa tasa se mueve poco aunque las alertas sean casi todas
falsas. Medido en el panel: a prevalencia 1%, ROC-AUC 0,868 contra PR-AUC 0,511.

**Lo que no viene de ningún paper** y es la métrica que más importa acá: **precisión@k**. Un
equipo investiga k casos por período; lo que decide si el sistema sirve es cuántos de esos k
eran de verdad. Es el análogo operativo de la función de potencia.

---

## Ley de Benford en auditoría

**Nigrini** — la desviación media absoluta (MAD) como criterio de conformidad; por debajo de
0,006 se considera conformidad cercana, por encima de 0,015 no conformidad.

**Qué se tomó:** el umbral para validar que el generador produce montos con la distribución de
primer dígito correcta. No es un adorno: **la desviación de Benford es en sí misma un detector
forense clásico**, así que un generador con `uniform()` vuelve trivial el problema. Los montos
salen de una lognormal, que la satisface por construcción.

---

## Nowcasting

**Regularización elástica (ElasticNet) con validación walk-forward.**

La decisión metodológica que importa no viene de un paper sino de la estructura del problema:
`TimeSeriesSplit` y no `KFold`, porque con folds aleatorios el criterio de selección mira
meses **posteriores** al bloque de validación, que es exactamente la información que no se
tiene al nowcastear.

El benchmark es un paseo aleatorio. Es el piso que cualquier modelo tiene que superar para
ser algo más que inercia, no un rival exigente.
