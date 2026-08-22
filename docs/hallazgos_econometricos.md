# Hallazgos econométricos — relato monetario-cambiario

**Muestra:** mensual desde 2017 · **Generado por:** `scripts/analisis.py` · **Módulo:** `platec/econometria.py`

Análisis del hilo causal del documento: **devaluación → traslado a precios**.
Los números de abajo se recalculan con cada corrida; acá se documenta la interpretación.

---

## 1. Estacionariedad y orden de integración

| Serie | ADF | KPSS | Veredicto |
|-------|-----|------|-----------|
| log(IPC) nivel | no rechaza (p≈0.94) | rechaza | **no estacionaria** |
| inflación mensual % | ambiguo (p≈0.07) | límite | ambiguo |
| log(TC) nivel | no rechaza (p≈0.94) | rechaza | **no estacionaria** |
| devaluación mensual % | rechaza (p≈0.00) | no rechaza | **estacionaria I(0)** |

**Orden de integración: log(IPC) ≈ I(2), log(TC) ≈ I(1).**

> **Punto econométrico fino:** el IPC resulta **I(2)** (hay que diferenciar dos veces para
> estacionarizar). Es típico de regímenes de inflación alta/acelerada: no solo el nivel de
> precios tiene tendencia, también la *tasa* de inflación. Esto tiene una consecuencia directa:
> **no se puede cointegrar directamente IPC (I(2)) con TC (I(1))** — son órdenes distintos.
> Por eso el test de Johansen abajo no encuentra cointegración estándar, y por eso el análisis
> del pass-through se hace sobre **variaciones** (series estacionarias), no sobre niveles.

## 2. Causalidad de Granger: devaluación → inflación

Significativa en el **rezago 2** (p≈0.006): una devaluación hoy ayuda a predecir la inflación
de ~2 meses después. Coherente con el mecanismo de traslado con demora.

## 3. Cointegración de Johansen (log IPC & log TC)

Rango 0 → **sin cointegración** en la muestra. Interpretación económica: el **tipo de cambio real
no es estable** en Argentina en este período (ciclos fuertes de apreciación/depreciación real),
sumado al desajuste I(2) vs I(1). Conclusión metodológica: modelar en **diferencias / variaciones**,
no en niveles.

## 4. Pass-through cambiario (TC → IPC)

Modelo de rezagos distribuidos sobre tasas mensuales, 6 meses. **R² ≈ 0.70.**

- **Impacto (mes 0): ~15%** de la devaluación pasa a precios de inmediato.
- **Acumulado a 6 meses: ~53%.** El traslado es *front-loaded* (se concentra en los primeros meses).

Un pass-through de ~0.5 a 6 meses es consistente con la literatura para Argentina. Es la clase de
número que la plataforma podrá responder ante "si el dólar sube 10%, ¿cuánta inflación agrega?"
(≈5 pp acumulados en medio año, con este modelo).

## 5. VAR de la cadena monetaria (dinero → dólar → precios → actividad)

VAR estimado sobre la cadena `[riesgo país, base monetaria, TC mayorista, IPC, EMAE]` en log-diferencias
mensuales (variaciones %). Se usa el **mayorista**, no el oficial: es el que enfrentan los
importadores, por donde entra el traslado a costos. Johansen sigue dando **rango 0** sobre los niveles con las cinco series
(§3), así que el VAR en diferencias es la especificación correcta y no corresponde un VECM.

La **respuesta acumulada del IPC a un shock de 1 d.e. en el TC** es *front-loaded* y consistente
con el pass-through: **~5 pp al año**. Pero el intervalo es ancho — a 12 meses ronda
**[0.3, 9.3] pp (95%)**: con ~110 observaciones mensuales el dato alcanza para afirmar que el
traslado existe y es rápido, no una magnitud precisa. La regresión de rezagos distribuidos (§4)
da un número más cerrado sólo porque impone que el dólar es exógeno; el VAR no necesita ese
supuesto y paga esa honestidad con incertidumbre visible.

**Las bandas se calculan con bootstrap de residuos propio** (Runkle 1987; Lütkepohl 2005, §3.7),
no con las bandas Monte Carlo de statsmodels: en esta versión (0.14.6 + numpy 2.x) `irf_resim`
devuelve las réplicas idénticas entre sí (desvío ~1e-15) y el intervalo colapsa sobre el punto
—un intervalo de ancho cero que miente con cara de rigor—. Es un intervalo percentil simple, sin
la corrección de sesgo de Kilian (1998): en muestras cortas tiende a subcubrir, leerlo como orden
de magnitud.

**Sensibilidad al orden de Cholesky.** La identificación impone una cadena causal contemporánea
que los datos no identifican. Bajo los tres ordenamientos probados la magnitud es robusta aquí
(~5.2 pp al horizonte final), pero el signo puede darse vuelta si se supone que los precios
se mueven antes que el dólar. El orden del relato (riesgo → dinero → dólar → precios → actividad)
es un supuesto económico, no un hallazgo.

## 5b. Riesgo país en el VAR: el canal es la actividad, no los precios

Incorporado 2026-08-22. `riesgo_pais` (EMBI+, diario desde 1999) entra a la cadena en
log-diferencias mensuales. **Pre-testing:** I(0) limpio en diferencias (ADF p=0,000;
KPSS p=0,096), VAR(2) por AIC, estable, n=112, 11 parámetros por ecuación.

**Va primero en el orden de Cholesky, y la justificación es empírica.** En el test de
Granger dentro del sistema ninguna variable precede al riesgo país (todos los p > 0,13:
TC 0,56 · IPC 0,49 · base 0,16 · EMAE 0,18), mientras que él sí precede a la actividad
(p = 0,0026 en el rezago 1). Es la más exógena de las cinco en sentido de Granger.

**Robustez del resultado previo.** Agregar la quinta variable **no rompe el pass-through**:
la respuesta acumulada del IPC al shock cambiario pasa de 4,99 pp (4 variables) a
**5,18 pp**, significativa en los 13 horizontes en ambas especificaciones.

**Lo que el riesgo país NO explica.** Hacia el TC mayorista y hacia el IPC, las bandas
bootstrap contienen al cero en **los 13 horizontes, bajo cualquier ordenamiento**. Peor
todavía, el punto estimado hacia el TC se mueve de **+1,70 pp** a **+0,60 pp** con solo
mover el riesgo país del primer al último lugar del orden de Cholesky. Casi todo el
efecto aparente sobre el dólar era **correlación contemporánea, no dinámica** — que es
exactamente el artefacto que el panel de sensibilidad existe para detectar.

**Lo que sí explica.** El canal hacia la **actividad** sobrevive:

| Ordenamiento | IRF acum. EMAE a 12m |
|---|---|
| riesgo → base → tc → ipc → emae | −0,80 pp |
| base → riesgo → tc → ipc → emae | −0,81 pp |
| base → tc → ipc → emae → riesgo | −0,56 pp |

Con bandas: **−0,80 pp [−1,35; −0,16]**, significativa en 12 de 13 horizontes. El signo es
negativo y significativo bajo los tres ordenamientos: la magnitud depende del supuesto de
identificación, el signo no. Es lo que hace creíble al resultado.

**Interpretación.** El riesgo soberano opera sobre el costo del crédito y la inversión, no
sobre el nivel de precios. Entró al modelo como candidato a explicar la dinámica cambiaria
y terminó explicando la real. La hipótesis previa —que el riesgo país anticipa la presión
cambiaria— **no se sostiene** en frecuencia mensual con esta muestra.

> **Advertencia de frecuencia.** El VAR es mensual y el riesgo país es diario. Al colapsar a
> fin de mes se pierde justamente la dinámica de alta frecuencia donde la relación
> riesgo–dólar probablemente vive. El resultado dice que *a un mes de plazo* el riesgo país
> no anticipa al TC; no dice que no lo haga en días. Un VAR diario TC–riesgo–brecha es el
> test pendiente.

## 5c. VAR diario por régimen: la hipótesis del riesgo país no sobrevive

Incorporado 2026-08-22. Sistema `[riesgo país, TC mayorista, brecha]` en log-diferencias
diarias, **3.264 días** con las tres series (01/2013 a 08/2026). La brecha entra como
`log(CCL/mayorista)`, no como brecha %: así queda definida aun cuando la brecha es
negativa (2016-19 llegó a −17%), y su diferencia es `Δlog(CCL) − Δlog(mayorista)`, que
no es colineal con `Δlog(mayorista)`.

**Se estima por régimen, no pooleado.** La brecha es un objeto distinto en cada uno:

| Régimen | n | Brecha media | Desvío |
|---|---|---|---|
| Cepo I (2013-15) | 697 | 45,0% | 13,2 |
| Sin cepo (2016-19) | 890 | **0,5%** | 1,5 |
| Cepo II (2019-23) | 1.036 | **81,8%** | 31,0 |
| Post-2023 | 641 | 15,9% | 15,0 |

Poolear un régimen sin brecha con uno de brecha 82% mezcla poblaciones distintas.

### El resultado

Sólo dos relaciones aguantan la grilla completa de rezagos:

| Régimen | Relación robusta (6/6) |
|---|---|
| Cepo I (2013-15) | riesgo país → brecha |
| Sin cepo (2016-19) | *ninguna* |
| Cepo II (2019-23) | *ninguna* |
| Post-2023 | **brecha → riesgo país** · **brecha → TC** |

**`Riesgo país → TC` no es robusta en ningún régimen.** La hipótesis que motivó incorporar
la serie —que el riesgo país anticipa la presión cambiaria— **no se sostiene en diario
tampoco**. Lo que sí lidera es la brecha, y lidera en las dos direcciones: al riesgo
soberano y al dólar oficial. Coincide con el Granger mensual, que desde el principio daba
la dirección brecha → riesgo país más fuerte que la inversa.

### Por qué hizo falta cambiar de test (y qué se corrigió)

El primer barrido usaba el método de la tabla mensual —`granger()` por rezago, quedarse
con el mínimo sobre 10— y daba `riesgo país → TC` con **p = 0,0005** en el régimen sin
cepo: aparentemente el hallazgo buscado. Un test de **Wald conjunto** sobre el mismo VAR
da **p = 0,047**, que no sobrevive la corrección por multiplicidad. El "hallazgo" era
selección post-hoc del rezago más favorable.

Peor todavía, el orden del VAR no está identificado en diario: **el AIC elige 3, 15 o 14
según dónde se ponga el tope**, mientras BIC elige 0 y HQIC 1. Reportar "el p al orden que
eligió el AIC" habría sido reportar un número arbitrario. Ejemplo, post-2023,
`riesgo país → TC` con Holm dentro del régimen:

| Rezago | 1 | 2 | 3 | 5 | 10 | 15 |
|---|---|---|---|---|---|---|
| p ajustado | 0,216 | 0,072 | **0,001** | 0,236 | 0,180 | **0,029** |

Significativa a 3 y 15, no a 1, 2, 5 ni 10. Es el patrón de un falso positivo. Contra eso,
`brecha → riesgo país` da p < 0,001 en los seis rezagos.

De ahí salieron dos funciones nuevas en `platec/econometria.py`:

- **`granger_sistema()`** — un test de Wald conjunto por par sobre el VAR ajustado, más
  corrección por multiplicidad (Holm). Reemplaza a la minimización sobre rezagos para
  armar tablas.
- **`granger_robusto()`** — el anterior repetido sobre una grilla de rezagos fijos. La
  columna `robusta` (significativa en todos) es la que hay que leer.

> **Efecto sobre §5.** Se reauditó la tabla mensual con el test conjunto: `TC → IPC` pasa
> de p=0,0054 a **0,0065** y `riesgo país → EMAE` de 0,0026 a **0,0085**. Las conclusiones
> del VAR mensual **se mantienen** — ahí la minimización sobre 6 rezagos no estaba
> fabricando nada. El problema era específico del diario, con 10 rezagos y más pares.

### Reservas

- Diferenciar una serie diaria con feriados trata el salto de viernes a lunes como un
  período. Es práctica estándar en datos financieros, pero introduce heterocedasticidad.
- La intersección de las tres series cubre el **91,8%** de los días hábiles del rango:
  los calendarios de BCRA y del mercado no coinciden exactamente.
- Post-2023 tiene n=641. Un VAR(15) son 46 parámetros por ecuación: la grilla de rezagos
  está justamente para no depender de esa especificación.

## 6. Curva de Phillips (trimestral)

Forma aumentada por expectativas: `π = α + β·u + γ·π₋₁`. **β_u ≈ −1.1 pero NO significativo
(p≈0.13)**. El signo es el esperado (más desempleo, menos inflación) pero la relación es
**estadísticamente plana** — resultado coherente con una inflación argentina dominada por
factores monetarios/cambiarios más que por el ciclo del mercado laboral. El R² alto (~0.65)
lo aporta la inercia (π₋₁), no el desempleo.

## 7. Nowcasting de inflación (ML)

`ElasticNet` con features de alta frecuencia (devaluación oficial/CCL, brecha, inercia),
validado **walk-forward** (ventana expansiva, 64 meses fuera de muestra):

- **RMSE modelo ≈ 1.68 vs. random walk ≈ 2.44 → ~31% menos error que el benchmark ingenuo.**
- Coeficientes: domina la inercia (`infl_l1`≈0.79); el pass-through del oficial aporta señal.
- Permite estimar el IPC del mes en curso antes de la publicación del INDEC.

> TAMAR se excluyó del nowcast: solo existe desde oct-2024 y truncaría el entrenamiento.

**Selección de la regularización.** (α, l1_ratio) se eligen con `TimeSeriesSplit` y no con
KFold: con folds contiguos el criterio de selección mira meses posteriores al bloque de
validación, justo la información que no está disponible al nowcastear. Dentro del
walk-forward la búsqueda se repite una vez por año de test y entremedio solo se reestiman
los coeficientes con la muestra ampliada — la penalidad óptima es estable mes a mes y
reelegirla en cada paso multiplicaba por 15 el tiempo de cómputo (15,7 s → 1,0 s) sin
mover el resultado (RMSE 1.68 vs. naive 2.42, +31%).

---

## Limitaciones y próximos refinamientos

- **Tipo de cambio real:** el pass-through usa TC nominal. Para RER bilateral falta CPI externo
  (FRED) — deflactar solo por precios locales (`platec.stats.deflactar`) es aproximado.
- **Quiebres estructurales:** la muestra 2017-2026 cruza cambios de régimen (2018-19, 2023-24).
  Conviene testear estabilidad de parámetros (Chow / ventanas móviles) antes de proyectar.
- **I(2) en el IPC:** para un modelo de largo plazo riguroso, evaluar sistema en la *tasa* de
  inflación o un VECM I(2), no el nivel.
- **Tabla de Granger mensual (§5):** sigue mostrándose con `p mínimo sobre 6 rezagos`.
  Reauditada con el test conjunto y las conclusiones no cambian, pero conviene migrar la
  tabla a `granger_sistema()` para que el criterio sea uno solo en todo el proyecto.
- **Riesgo país anterior a 2013:** el VAR diario arranca en 2013 porque lo limita el CCL.
  La serie de riesgo país tiene datos desde 1999 — un sistema `[riesgo, TC]` sin brecha
  podría usar 2002-2013 y cubrir la salida de la convertibilidad.
- **Nowcasting (Etapa 7):** con estas relaciones + variables de alta frecuencia (TC diario) se
  puede estimar el IPC del mes en curso antes de la publicación oficial.
