# Firmas sintéticas — un dataset que no se resuelva solo

**Módulos:** `platec/firmas_sinteticas.py`, `scripts/ingest_ratios_sectoriales.py` ·
**Tests:** `tests/test_firmas_sinteticas.py`

Estados contables de empresas **ficticias**, calibrados contra la estructura sectorial real
de la economía argentina, con etiqueta de verdad sobre qué firma ejecuta qué maniobra.

---

## 1. Por qué existe, y qué no es

Los reportes de operación sospechosa son confidenciales por ley en toda jurisdicción: no hay
datos etiquetados públicos. Por eso la literatura del área trabaja con simuladores (AMLSim,
SAML-D, AMLgentex). Esto es lo mismo, con dos diferencias: está calibrado contra Argentina y
está atado a un resultado que la propia plataforma estimó.

**No son empresas reales ni imitan a ninguna.** Los identificadores son `SINT-0001`, sin
nombre, sin CUIT, sin sector identificable a una firma concreta. Nada de lo que sale de acá
puede pasar por una presentación genuina, y eso es una restricción de diseño con test que la
fija, no un detalle.

## 2. La tensión con el resto de la plataforma

Todo el proyecto se apoya en una regla: **no inventamos números**. El narrador no puede
escribir una cifra que Python no calculó. Este módulo hace exactamente lo contrario, así que
se lo aísla por construcción:

1. **No persiste nada.** No hay tabla, no hay snapshot, no hay fila que pueda terminar al
   lado de un dato real. Se genera de forma determinística desde una semilla: la
   reproducibilidad se consigue guardando **un entero**, no un dataset. Hay un test que
   verifica que el módulo no escribe en disco.
2. **No entra al narrador como dato.** Si alguna vez se redacta sobre esto, el dossier tiene
   que declararlo sintético como advertencia de primera clase.
3. Lo único real que toca es `data/ratios_sectoriales.json`, que declara su fuente.
4. En el dashboard vive en una página aparte, con el aviso arriba de todo y no al pie.

## 3. Qué hace que no sea trivial

Un generador ingenuo produce datos que cualquier detector resuelve por la vía equivocada.
Cinco cosas evitan eso, y cada una tiene test:

| Propiedad | Por qué importa |
|---|---|
| **Articulación contable** | Si Activo ≠ Pasivo + Patrimonio, el detector separa firmas por un error de construcción, no por su comportamiento |
| **Ley de Benford** | Los datos contables reales la siguen; la desviación de Benford **es** un detector forense clásico. Con `uniform()` el problema se vuelve trivial. Los montos salen de una lognormal, que la satisface por construcción |
| **Estructura sectorial real** | Sin ella, «poca nómina» no tiene contra qué medirse |
| **Prevalencia baja** | En AML el orden real es 1 en 1.000. Un dataset balanceado es clasificación fácil, no detección |
| **La maniobra va a quien puede hacerla** | No se sobrefactura importaciones sin importar |

Esa última costó una versión entera. Repartiendo las maniobras al azar, la sobrefacturación
movía el margen de 0,96 a 0,95 y no significaba nada: quedaba diluida en firmas que apenas
comerciaban.

## 4. La calibración: datos oficiales, no intuición

`scripts/ingest_ratios_sectoriales.py` baja la **Cuenta de Generación del Ingreso** del INDEC
(dataset 323.1 de datos.gob.ar) y calcula, por sector CIIU:

- **margen operativo** = excedente de explotación bruto / valor agregado bruto
- **participación salarial** = remuneración al trabajo asalariado / valor agregado bruto

14 sectores, promediando ocho trimestres para captar la estructura y no la coyuntura.

> Los dos ratios **no suman 100%**: el VAB también incluye ingreso mixto e impuestos netos de
> subsidios, que pueden ser negativos. En Electricidad, gas y agua los subsidios hacen que la
> suma pase del 100%, y eso es correcto.

## 5. Qué deja cada maniobra en los libros

Normalizado por la estructura de cada sector (1,00 = igual a lo normal de su actividad).
«Crec. máx.» es el mayor salto interanual de facturación de la firma.

| Tipología | Margen op. | Nómina | Ing./act. fijo | Pasivo/patr. | Caja/ing. | Crec. máx. |
|---|---|---|---|---|---|---|
| (sin maniobra) | 0,96 | 1,00 | 2,03 | 1,11 | 0,075 | 17% |
| pantalla | 1,78 | **0,07** | **43,86** | 1,10 | 0,075 | 18% |
| fachada | 1,36 | 0,68 | 2,88 | 0,96 | 0,051 | 56% |
| efectivo | 1,24 | 0,76 | 2,68 | 1,13 | **0,277** | 37% |
| subfacturación exportaciones | **0,68** | 1,18 | 1,74 | 1,23 | 0,091 | 17% |
| sobrefacturación importaciones | 0,90 | 1,00 | 1,90 | 1,09 | 0,071 | 18% |
| compras desproporcionadas | 0,95 | 1,00 | 0,70 | **8,12** | 0,073 | 19% |
| nueva / reactivada | 0,95 | 1,03 | 1,93 | 1,28 | 0,074 | **1.749%** |

**Ninguna se identifica con una sola razón**, y dos son deliberadamente difíciles:

- La **fachada** conserva nómina y planta porque son reales. No hay anomalía estructural que
  buscar: sólo factura más de lo que esa capacidad instalada explica, y su margen mejora
  porque el dinero inyectado no tiene costo. **Un dataset con sólo pantallas sobreestima
  cualquier detector.**
- La **entidad nueva o reactivada** es indistinguible en corte transversal — mirá su fila:
  margen 0,95, nómina 1,03, todo normal. Su anomalía es la **trayectoria**, y eso obliga a un
  detector a usar la historia de la firma y no una foto.

La **subfacturación** comprime el margen, pero eso lo comparte con cualquier empresa que
simplemente gana poco: el estado contable la **señala y no la identifica**. Lo que la
identifica es comparar contra lo que declara la contraparte, que es lo que hace
[`comercio_espejo`](comercio_espejo.md) en agregado.

> **Supuesto que conviene tener presente.** La subfacturación omite ingresos y deja los costos
> en los libros, y por eso comprime el margen. Una firma que además maneje los costos
> correspondientes por fuera mostraría un margen menos comprimido: este canal está modelado en
> el extremo detectable del rango.

### De dónde sale cada tipología

Cada una cita su indicador en el código (`TIPOLOGIAS[...].fuente`), y hay un test que verifica
que ninguna maniobra exista sin respaldo:

| Tipología | Fuente |
|---|---|
| pantalla | GAFI/Egmont 2021, estructural: *«lacks regular payroll transactions in line with the number of stated employees»* |
| fachada | GAFILAT 2009-2016 §V, vehículos corporativos (§54, §64, §65, §69) |
| efectivo | GAFILAT 2009-2016 §56, comercios pantalla para colocación |
| sobrefacturación | GAFI/Egmont 2021, actividad: *«consistently displays unreasonably low profit margins»* |
| compras desproporcionadas | GAFI/Egmont 2021, actividad: *«purchases clearly exceed the economic capabilities of the entity»* |
| nueva / reactivada | GAFI/Egmont 2021: *«newly formed or recently re-activated trade entity engages in high-volume… activity»* + *«unexplained periods of dormancy»* |

**De los 35 indicadores de GAFI, sólo unos siete son observables en un estado contable
anual**: el 80% son de documentos aduaneros y de movimientos de cuenta, que un balance no
contiene. Lo que se modela acá es esa minoría, y la limitación es del objeto, no del generador.

## 6. El puente con el resultado macro

La intensidad de la subfacturación se calibra para que la **discrepancia agregada del panel**
reproduzca el β que la plataforma estimó sobre datos reales: **+0,0589** puntos porcentuales
de discrepancia por punto de brecha ([`comercio_espejo.md`](comercio_espejo.md) §6).

Se calibra **midiendo, no despejando**. La versión analítica erraba un 20% sistemático porque
la maniobra no está activa en todos los ejercicios y porque el denominador son las
exportaciones ya reducidas — ninguna de las dos cosas se conoce antes de generar. Se genera,
se mide, se reescala y se regenera con el mismo sorteo.

**La sobrefacturación no escala con la brecha, y eso es el hallazgo, no una omisión.** El
contraste macro da β = +0,009 con p = 0,68 en ese canal: un cero limpio. Sobrefacturar exige
acceso al dólar oficial, que es lo que el cepo raciona vía DJAI, SIMI o SIRA; subfacturar no
exige permiso de nadie. Que el generador hiciera crecer las dos maniobras con la brecha
contradiría la evidencia de la propia plataforma.

### Una implicancia que salió sola

La calibración **no es factible con prevalencias bajas**, y perseguir eso destapó un
resultado. Si se omite el 5,9% de las exportaciones y ninguna firma omite más del 60% de las
suyas, entonces al menos el **9,8% del valor exportado** pasa por manipuladores.

El umbral empírico coincide con el aritmético: la calibración se vuelve factible justo cuando
los subfacturadores cruzan ese 9,8% de las exportaciones del panel.

| Prevalencia | Firmas | % del valor exportado | Logrado | Objetivo | ¿Calibra? |
|---|---|---|---|---|---|
| 10% | 36 | 4,5% | 0,0315 | 0,0589 | no |
| **20%** | 70 | **9,8%** | 0,0544 | 0,0589 | **sí** |
| 30% | 125 | 22,0% | 0,0595 | 0,0589 | sí |

**El β estimado sobre datos reales implica cuánto comercio tiene que estar comprometido** para
que la discrepancia observada exista. Eso es un resultado, no un parámetro — y la primera
versión lo tapaba topeando la intensidad en silencio, lo que además producía firmas con margen
operativo **negativo**: un estado contable absurdo que habría delatado la maniobra por la vía
equivocada.

## 7. El detector, y lo que encontró

`platec/deteccion.py` arma las características observables de cada firma —razones de un
balance y un estado de resultados, normalizadas por sector— y evalúa un clasificador con
validación cruzada. La unidad es la **firma**, no el ejercicio: se investiga una empresa, no
su año fiscal 2022, y evaluar por ejercicio filtraría porque los otros años de la misma firma
estarían en el entrenamiento.

**No se reporta exactitud.** Con prevalencia del 2%, predecir «todas limpias» acierta el 98%.
Se reportan PR-AUC (cuyo piso de azar es la prevalencia, no 0,5), precisión@k —un equipo
investiga k casos y lo que importa es cuántos eran de verdad— y ROC-AUC con la advertencia de
que **bajo desbalance extremo exagera**: se apoya en la tasa de falsos positivos, y con 98% de
negativos esa tasa se mueve poco aunque las alertas sean mayoritariamente falsas.

| Prevalencia | PR-AUC | ROC-AUC | Precisión@k | Azar |
|---|---|---|---|---|
| 20% | 0,919 | 0,955 | 83,6% | 0,200 |
| 5% | 0,833 | 0,937 | 78,0% | 0,050 |
| 2% | 0,785 | 0,930 | 77,5% | 0,020 |
| 1% | 0,511 | 0,868 | 52,5% | 0,010 |

### La fuga que destapó

La primera corrida dio **PR-AUC 0,89 con prevalencia 2%**, que para un problema de AML es
demasiado bueno para ser cierto. La causa estaba en el generador:

1. **Soportes disjuntos.** La intensidad exportadora de las limpias se sorteaba en
   [0,00 – 0,35] y la de las subfacturadoras en [0,45 – 0,85]. Cero solapamiento:
   `exportador > 0,40` las identificaba perfecto. El clasificador aprendía a reconocer el
   sorteo, no la maniobra.
2. **Variación nula entre ejercicios.** La intensidad comercial era idéntica todos los años,
   así que su desvío era exactamente cero para toda firma limpia y se volvía el mejor
   predictor del panel.

Corregido: ahora una parte de las firmas son comerciantes —limpias o no— y las manipuladoras
salen de esa misma población, con ruido año a año. Comerciar mucho es informativo, no
determinante. El PR-AUC bajó a 0,785.

> **Un detector que anda demasiado bien es un diagnóstico sobre el dataset, no un logro.** Hay
> un test que falla si una sola característica se lleva más del 95% de la importancia.

### Qué maniobra se ve y cuál no

Recall a prevalencia 2%, con presupuesto igual al número de manipuladoras:

| Tipología | Recall |
|---|---|
| efectivo | 100% |
| nueva / reactivada | 100% |
| pantalla | 93% |
| fachada | 80% |
| compras desproporcionadas | 75% |
| subfacturación exportaciones | 65% |
| **sobrefacturación importaciones** | **0%** |

**El cero no es un bug.** Aislada en su propio panel, la sobrefacturación da PR-AUC 0,101
contra un azar de 0,030: detectable, pero apenas. El número que lo explica es que **la
diferencia de margen contra las limpias vale 0,06 desvíos** de la dispersión natural de
rentabilidad entre empresas. Un margen comprimido lo comparte con cualquier empresa que
simplemente gana poco, y su intensidad importadora la comparte con los importadores legítimos.
En un panel con todas las tipologías y presupuesto acotado, el detector gasta las alertas en
las que sí se ven y nunca llega a estas.

Es la confirmación cuantitativa de lo que el indicador de GAFI ya sugería: *«consistently
displays unreasonably low profit margins»* es una señal real y **confundida**.

> Y el contrapunto: un panel con **sólo** empresas pantalla da **PR-AUC 1,000**. Cualquier
> detector evaluado ahí queda sobreestimado. Es exactamente la razón de haber agregado la
> fachada.

### En el dashboard

La página **🧪 Firmas sintéticas** trae la evaluación completa: PR-AUC contra su azar, ROC-AUC
con la advertencia puesta, precisión@k, la **curva de precisión según el presupuesto de
alertas** —qué fracción de las k alertas sería real, que es lo que decide cuánto trabajo se
desperdicia— y el recall por tipología.

Avisa cuando hay menos de 30 firmas con maniobra: ahí las métricas son ruidosas por muestra
chica y no por peor detección. Con el default de 500 firmas al 2% hay **diez** positivas y el
PR-AUC cae a 0,25; con 2.000 firmas sube a 0,72. Es la misma disciplina que la función de
potencia del test de estabilidad: un número sin saber cuánto puede moverse no dice nada.

## 8. Lo que este dataset no prueba

Un detector entrenado acá encuentra las maniobras que uno mismo inyectó. **No dice nada sobre
el lavado real.** Sirve para:

- comparar métodos entre sí sobre un terreno común;
- medir **potencia** — cuán chica puede ser una maniobra y todavía detectarse, la misma
  disciplina que se aplicó al test de estabilidad del VAR;
- desarrollar el pipeline sin esperar datos que no van a llegar.

No sirve como evidencia sobre la economía argentina. Ver
[preguntas abiertas](notas/preguntas-abiertas.md) §3.

```bash
python3 scripts/ingest_ratios_sectoriales.py     # calibración (una vez, cambia poco)
```

```python
from platec import firmas_sinteticas as fs
df = fs.generar(n_firmas=1500, prevalencia=0.30, brecha=100.0, semilla=7)
fs.articula(df)                      # el balance cierra
fs.desvio_benford(df["ingresos"])    # conformidad de primer dígito
fs.discrepancia_exportadora(df)      # el agregado, contra el beta macro
fs.share_exportador_minimo(100.0)    # la implicancia aritmética del beta
df.attrs["calibrado"]                # si el objetivo era alcanzable
```
