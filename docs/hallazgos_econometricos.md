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

## 5. VAR e impulso-respuesta (devaluación → inflación)

VAR(4) estable sobre `[devaluación, inflación]` mensual. La **función impulso-respuesta
ortogonalizada** (Cholesky, devaluación primero) muestra la respuesta acumulada de la
inflación a un shock de 1σ en la devaluación: **~2 pp al mes 1, ~4 pp al mes 6, ~4.9 pp
al año**. Confirma la transmisión *front-loaded* que ya mostraba el pass-through, ahora
en un marco dinámico multivariado.

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

---

## Limitaciones y próximos refinamientos

- **Tipo de cambio real:** el pass-through usa TC nominal. Para RER bilateral falta CPI externo
  (FRED) — deflactar solo por precios locales (`platec.stats.deflactar`) es aproximado.
- **Quiebres estructurales:** la muestra 2017-2026 cruza cambios de régimen (2018-19, 2023-24).
  Conviene testear estabilidad de parámetros (Chow / ventanas móviles) antes de proyectar.
- **I(2) en el IPC:** para un modelo de largo plazo riguroso, evaluar sistema en la *tasa* de
  inflación o un VECM I(2), no el nivel.
- **Nowcasting (Etapa 7):** con estas relaciones + variables de alta frecuencia (TC diario) se
  puede estimar el IPC del mes en curso antes de la publicación oficial.
