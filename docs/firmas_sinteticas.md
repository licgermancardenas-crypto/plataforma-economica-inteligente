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

Normalizado por la estructura de cada sector (1,00 = igual a lo normal de su actividad):

| Tipología | Margen op. | Nómina | Caja/ing. | Import/costos |
|---|---|---|---|---|
| (sin maniobra) | 0,95 | 1,01 | 0,076 | 0,220 |
| sobrefacturación importaciones | 0,89 | 1,01 | 0,073 | **0,725** |
| subfacturación exportaciones | **0,63** | 1,19 | 0,087 | 0,193 |
| pantalla | 1,76 | **0,06** | 0,069 | 0,228 |
| efectivo | 1,23 | 0,77 | **0,311** | 0,205 |

**Ninguna se identifica con una sola razón.** La pantalla es la más visible: factura sin
nómina ni activo fijo. La sobrefacturación sólo se separa mirando cuánto importa respecto de
sus pares — su margen comprimido no alcanza. Y la subfacturación comprime el margen, pero eso
lo comparte con cualquier empresa que simplemente gana poco: **el estado contable la señala y
no la identifica**. Lo que la identifica es comparar contra lo que declara la contraparte, que
es lo que hace [`comercio_espejo`](comercio_espejo.md) en agregado.

> **Supuesto que conviene tener presente.** La subfacturación omite ingresos y deja los costos
> en los libros, y por eso comprime el margen. Una firma que además maneje los costos
> correspondientes por fuera mostraría un margen menos comprimido: este canal está modelado en
> el extremo detectable del rango.

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

## 7. Lo que este dataset no prueba

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
