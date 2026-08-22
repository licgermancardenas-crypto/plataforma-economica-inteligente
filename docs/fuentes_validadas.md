# Fuentes de datos validadas — Plataforma Económica Inteligente

**Validado:** 2026-08-22 · **Script:** `scripts/validate_sources.py` · **Estado:** 11/11 OK

Este documento es la fuente de verdad de qué serie exacta consume el pipeline.
Corrige y precisa el *Anexo técnico* del PDF de planificación.

---

## 1. Catálogo canónico de indicadores núcleo

| # | Indicador | Fuente | ID / Endpoint | Frecuencia | Unidad | Último dato |
|---|-----------|--------|---------------|-----------|--------|-------------|
| 1 | IPC nivel general (nacional) | INDEC / datos.gob.ar | `148.3_INIVELNAL_DICI_M_26` | Mensual | Índice base dic-2016 | 2026-06 |
| 1b| IPC núcleo (nacional) | INDEC / datos.gob.ar | `148.3_INUCLEONAL_DICI_M_19` | Mensual | Índice base dic-2016 | 2026-06 |
| 2 | Tipo de cambio oficial/MEP/CCL/blue | **argentinadatos** | `/v1/cotizaciones/dolares/{oficial,bolsa,contadoconliqui,blue}` | Diaria | ARS/USD | histórico desde 2011 |
| 2c| TC mayorista de referencia | BCRA Monetarias v4.0 | `idVariable=5` | Diaria | ARS/USD | 2026-07-29 |
| 2d| TC (tiempo real, fallback) | dolarapi | `/v1/dolares/{oficial,bolsa,...}` | Diaria | ARS/USD | tiempo real |
| 3 | Tasa de referencia (TAMAR priv., TNA) | BCRA Monetarias v4.0 | `idVariable=44` | Diaria | % nominal anual | 2026-07-28 |
| 4 | EMAE original (base 2004) | INDEC / datos.gob.ar | `143.3_NO_PR_2004_A_21` | Mensual | Índice 2004=100 | 2026-05 |
| 4b| EMAE desestacionalizada | INDEC / datos.gob.ar | `302.3_S_DESEST_NRAL_0_S_19` | Mensual | Índice 2004=100 | 2026-04 |
| 5 | Reservas internacionales | BCRA Monetarias v4.0 | `idVariable=1` | Diaria | Millones USD | 2026-07-27 |
| 5b| Base monetaria | BCRA Monetarias v4.0 | `idVariable=15` | Diaria | Millones ARS | 2026-07-27 |
| 6 | Tasa de desocupación (nacional) | INDEC/EPH · datos.gob.ar | `42.3_EPH_PUNTUATAL_0_M_30` | Trimestral | Fracción (×100 = %) | 2026-Q1 |

## 1b. Bloque fiscal — Secretaría de Hacienda (Ministerio de Economía)

Incorporado 2026-08-22. Publica en la **misma** API de Series de Tiempo que INDEC, así que
no requirió fetcher nuevo: son filas de catálogo. Por eso el `source_id` pasó de
`indec_datosgob` a **`datosgob_series`** — la fuente es la API del Estado, no un organismo.

| Serie | ID | Frecuencia | Unidad | Desde | Último |
|-------|----|-----------|--------|-------|--------|
| Resultado primario SPN (IMIG) | `452.3_RESULTADO_RIO_0_M_18_54` | Mensual | Millones ARS | 2016-01 | 2026-06 |
| Intereses netos SPN (IMIG) | `452.3_INTERESES_TOS_0_M_15_62` | Mensual | Millones ARS | 2016-01 | 2026-06 |
| Resultado financiero SPN (IMIG) | `452.3_RESULTADO_ERO_0_M_20_25` | Mensual | Millones ARS | 2016-01 | 2026-06 |
| Recaudación tributaria total | `172.3_TL_RECAION_M_0_0_17` | Mensual | Millones ARS | 1997-01 | 2026-07 |

**Control de integridad** (verificado sobre las 126 observaciones ingeridas):
`resultado_primario − intereses_netos = resultado_financiero`, con error máximo **0,0000**.

**Advertencias de uso:**
- Son **flujos mensuales**, no acumulados, pese a que el catálogo etiqueta la recaudación
  como "Anuales" (artefacto de la descripción, no del dato).
- Están en **pesos nominales**. Con inflación de tres dígitos, un VAR en niveles nominales
  estima inflación, no política fiscal: deflactar por IPC o expresar en % del EMAE.
- `resultado_financiero` es **colineal exacto** con `resultado_primario + intereses_netos`.
  En un VAR entra esa serie **o** las otras dos, nunca las tres.
- El IMIG **no publica** los agregados "Ingresos totales" ni "Gastos primarios" como serie
  propia: solo los componentes desagregados y los tres resultados. Si se necesitan los
  agregados hay que sumar componentes, o usar `recaudacion_total` como proxy de ingresos
  (más larga y de publicación más temprana).
- Muestra corta: 126 meses desde 2016-01. Alcanza para un VAR mensual parsimonioso
  (2-3 rezagos, pocas variables), no para uno saturado.

Endpoints base:
- **BCRA:** `https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias` (catálogo) y `/Monetarias/{id}?desde=&hasta=` (serie).
- **datos.gob.ar:** `https://apis.datos.gob.ar/series/api/series?ids={id}&format=json`.
  Cuidado al pedir **varios ids de distinta frecuencia en una misma request**: la API
  colapsa a la frecuencia más gruesa y promedia. La ingesta pide un id por request.
- **dolarapi:** `https://dolarapi.com/v1/dolares/{tipo}`.

---

## 2. Correcciones al Anexo técnico del PDF

1. **dolarapi:** el PDF documenta `/api/dolar/*`; el endpoint vigente es **`/v1/dolares/*`**.
   Además dolarapi **solo devuelve el valor actual** (sin historia) → para la serie histórica
   de TC se usa **argentinadatos** (oficial/MEP/CCL/blue desde 2011) y **BCRA id=5** para el
   TC mayorista de referencia. dolarapi queda como fallback en tiempo real. Sin esto la brecha
   histórica arrancaría recién hoy.
2. **Desempleo (EPH):** el anexo lo daba como el indicador problemático, sin API y con
   necesidad de scrapear PDFs del INDEC. **Falso a hoy:** existe la serie nacional
   trimestral `42.3_EPH_PUNTUATAL_0_M_30` vigente (llega a 2026-Q1) en datos.gob.ar.
   → El desempleo se ingiere como cualquier otra serie; el Plan B queda solo como respaldo.
3. **Tasa de política monetaria:** en 2026 los **pases pasivos están en 0** — el instrumento
   clásico ya no rige. Se adopta **TAMAR bancos privados (TNA), `idVariable=44`** como proxy
   de tasa de referencia. *Decisión a revisar según el régimen monetario vigente.*
4. **BCRA v4.0:** el último valor viene en `ultValorInformado` / `ultFechaInformada` (no `valor`).

---

## 3. Gotchas de formato a manejar en la ingesta

- **Desempleo en fracción:** la serie devuelve `0.078` para 7,8% (unidad etiquetada "Porcentaje"
  pero almacenada como ratio). **Multiplicar ×100** al normalizar.
- **BCRA / SSL:** la cadena de certificados del BCRA puede no validar; el ingestor debe
  contemplar `verify=False` como fallback controlado (no global).
- **BCRA `idVariable=44` vs `45`/`136`/`137`:** son variantes TAMAR (TNA vs TEA, privados vs
  públicos+privados). Fijar cuál se usa y no mezclarlas.

---

## 4. Consideraciones econométricas que condicionan el esquema de datos

Estas nacen del objetivo (herramienta de análisis con módulo de econometría, sección 10 del PDF)
y deben resolverse en la capa de almacenamiento, no después:

1. **Mezcla de frecuencias.** Diaria (TC, tasa, reservas, base) / mensual (IPC, EMAE) /
   trimestral (desempleo). Guardar cada serie en su frecuencia nativa **y** exponer vistas
   remuestreadas a frecuencia común (fin de mes / promedio mensual) para VAR, Granger, VECM.
2. **Nominal vs real.** El tipo de cambio real y el pass-through requieren deflactar por IPC:
   IPC y TC deben estar perfectamente alineados en el tiempo.
3. **Estacionariedad.** Casi todas las series son I(1). El pipeline analítico debe correr
   ADF + KPSS antes de cualquier VAR; TC–IPC es un caso de **cointegración → VECM**, no VAR en niveles.
4. **Quiebres estructurales / calidad de datos.** El IPC del período **2007–2015 (INDEC intervenido)**
   no es estadísticamente creíble. Toda serie larga necesita una **bandera de calidad** por tramo,
   o los modelos estimarán ruido. Idem rebases de índice.
5. **Desestacionalización X-13.** `statsmodels` la soporta pero requiere el binario
   **X-13ARIMA-SEATS** del Census Bureau instalado aparte. (Para EMAE ya existe la variante
   desestacionalizada oficial `302.3_...`, útil como contraste.)

---

## 5. Reproducir la validación

```bash
python3 scripts/validate_sources.py
# Reporte JSON: data/raw/validation_report.json
```
