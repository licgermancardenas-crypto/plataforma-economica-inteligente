# Capa de IA — cómo se admite un LLM en una herramienta de análisis

**Módulo:** `platec/narrador.py` · **Tests:** `tests/test_narrador.py` · **Etapa 8**

Este documento explica una decisión de diseño, no una funcionalidad. El valor de esta
plataforma es el rigor: si el LLM puede inventar un número o deslizar una causalidad que
los datos no sostienen, la capa de IA no agrega análisis, lo contamina. Todo lo que sigue
existe para que eso sea imposible por construcción y no meramente improbable.

---

## 1. El principio: el LLM no calcula

La división del trabajo es estricta:

| Quién | Qué hace |
|---|---|
| `platec` (Python) | Calcula. Toda cifra sale de `data`, `stats`, `insights`, `econometria`, `gobiernos`. |
| El LLM | Redacta. Recibe un conjunto **cerrado** de hechos ya calculados y escribe prosa sobre eso. |

El vehículo es el `Dossier`: título, contexto, una lista de `Hecho` (etiqueta, valor,
unidad) y una lista de advertencias. Lo que no está en el dossier no puede aparecer en el
texto sin que la verificación lo marque.

Esto también decide qué **no** hace el módulo: no hay chat, no hay preguntas libres sobre
la economía argentina, no hay recuperación de documentos. Un chat sobre datos macro es
justamente la forma en que un LLM entra a una herramienta de análisis a responder de
memoria. Acá cada respuesta está anclada a un dossier construido en Python.

## 2. Verificación numérica post-hoc

Después de generar, `verificar()` extrae **todos** los números del texto y los contrasta
contra los valores del dossier. El criterio es el redondeo: un número escrito con `d`
decimales está respaldado si algún valor del dossier redondeado a `d` decimales coincide.
Así el modelo puede escribir «2,1%» donde el dato es 2,14 —redondear es legítimo— pero no
puede escribir nada más.

La verificación es **deliberadamente estricta**. Se marcan como huérfanos:

- **Números inventados.** El caso obvio.
- **Reescalados.** Pasar «45.511 millones de dólares» a «45,5 mil millones» es una
  división, y las divisiones son del lado de Python.
- **Valores derivados.** Restar dos hechos del dossier para obtener un tercero también es
  calcular, aunque los dos operandos estén autorizados.

La única excepción son los **años**: sin ellos no se puede escribir una oración sobre
series temporales. La excepción está acotada por dos lados, porque el rango de los años se
superpone con magnitudes reales: un año con decimales —«2016,0»— no es un año sino una
magnitud, y un número con separador de miles —«2.052»— tampoco, porque un año no se
escribe así. Sin esa segunda condición, un riesgo país inventado en puntos básicos (que
vive entre 700 y 7.000) se haría pasar por año y saldría sin marcar.

Si aparece un huérfano se reintenta una vez, diciéndole al modelo **cuál** número está de
más, no un reproche genérico. Si insiste, la lectura se devuelve igual con
`verificado=False` y la lista de huérfanos, y la UI la muestra marcada en ámbar con la
advertencia. Ocultar el texto sería peor: dejaría al usuario sin saber que el modelo falla
en ese dossier.

> **El costo de ser estrictos son los falsos positivos.** Si el modelo escribe una
> magnitud legítima en una unidad distinta, se marca igual. Es el sesgo correcto para una
> herramienta de análisis: un texto marcado pide revisión, un número inventado sin marcar
> se propaga a una conclusión.

## 3. Determinismo por caché, no por temperatura

Una herramienta de análisis que devuelve un texto distinto cada vez que se abre la página
no es reproducible, y sin reproducibilidad no hay análisis que valga.

El reflejo sería bajar la temperatura a 0. **No se puede:** los modelos actuales de la
familia Opus eliminaron el parámetro `temperature` y lo rechazan con un 400. Y aun cuando
existía, temperatura 0 nunca garantizó determinismo real.

El determinismo se consigue cacheando: `sha256(versión del prompt + modelo + texto del
dossier + pregunta) → texto`. Mismos datos, mismo texto, hasta que los datos cambien. Tres
consecuencias que importan:

- Los **caveats entran al hash**: si cambia una advertencia, la lectura vieja ya no vale.
- `PROMPT_VERSION` entra al hash: al tocar las reglas de redacción se invalidan todas las
  lecturas anteriores, porque fueron escritas con otras reglas.
- El dashboard **no llama al modelo en cada rerun**. Streamlit reejecuta el script ante
  cualquier interacción; llamar ahí sería pagar una redacción por click. Si hay lectura
  cacheada para esos datos se muestra sola; si no, hay que pedirla con un botón.

El estado de verificación viaja con el texto en el caché: una lectura no verificada sigue
marcada al recuperarse.

## 4. Degradación limpia

Sin credenciales, `disponible()` devuelve `False`, el SDK ni se importa (el import es
diferido) y el dashboard muestra el panel de **lectura automática** de `platec/insights.py`,
que es determinístico y no necesita API. La capa de IA es un agregado, nunca un requisito
para ver el tablero — el mismo criterio que hizo que el snapshot versionado reemplazara la
ingesta en el arranque.

Los tests no tocan la red ni requieren el SDK instalado: el cliente se inyecta como doble.

## 5. Configuración

```bash
export ANTHROPIC_API_KEY="..."        # local
```

En Streamlit Community Cloud va como *secret* del deploy (`ANTHROPIC_API_KEY`); el
dashboard lo pasa de `st.secrets` al entorno, que es donde lo busca `platec.narrador`. El
módulo no conoce Streamlit a propósito: se usa igual desde un script o un notebook.

```python
from platec import narrador as nar

d = nar.dossier_serie("ipc_general")
print(d.a_texto())                    # exactamente lo que verá el modelo
lec = nar.redactar(d)
print(lec.texto, lec.verificado, lec.numeros_huerfanos)
```

**Modelo:** `claude-opus-5`, esfuerzo `medium`, con pensamiento adaptativo. El techo de
tokens (`MAX_TOKENS`) es holgado para la prosa porque el pensamiento consume del mismo
presupuesto; una respuesta truncada se trata como error y no como lectura.

## 6. Dossiers econométricos

`dossier_canal` y `dossier_nowcast` extienden la capa al VAR, el pass-through y el
nowcast. La regla que los organiza es que **la estimación puntual sola no es un
resultado**: si al dossier entra únicamente el número central, el modelo escribe una
oración categórica sobre él y la prosa queda más segura que la evidencia. Entonces entran
como hechos de primera clase los dos límites del intervalo, **su amplitud**, en cuántos
horizontes excluye al cero, y **la misma respuesta bajo cada ordenamiento de Cholesky
alternativo**. Recién con eso la prosa puede separar qué parte de la conclusión es
evidencia y qué parte es supuesto de identificación.

**Se precalcula todo lo que el modelo querría restar.** La amplitud del intervalo
(`superior − inferior`) y la distancia entre el nowcast y el último dato oficial son
cuentas: si no vienen hechas, el modelo las hace y el verificador las marca como
derivadas — correctamente, y de forma inútil, porque el número era cierto. La regla
general: cualquier magnitud que la lectura natural va a mencionar tiene que existir como
`Hecho`, no como resta implícita.

**Las unidades se fijan del lado de Python.** `PassThrough.acumulado` es una fracción
(0,534) y la prosa natural dice «53,4%». Escribir eso desde 0,534 es un reescalado, que es
exactamente lo que el verificador rechaza. El ×100 va en el constructor del dossier.

**Reciben los objetos ya estimados, no los nombres de las series.** Mismo criterio que
`dossier_gobierno`: el dossier describe los números que están en pantalla, no unos
parecidos recalculados por su cuenta. Además tipan por comportamiento, así que `narrador`
sigue sin importar `statsmodels` ni `scikit-learn` — importa en el arranque del dashboard
y ese import cuesta segundos. Hay un test que lo verifica en un intérprete limpio.

**Qué se deja afuera a propósito.** La tabla de Granger mensual reporta el «p mínimo sobre
6 rezagos»: es el mejor de seis pruebas sin corregir por comparaciones múltiples, no un
p-valor, y el propio proyecto lo tiene marcado como criterio a migrar. Los coeficientes
del ElasticNet están sin estandarizar, así que sus magnitudes no son comparables entre
variables de escalas distintas. Ninguno de los dos entra: **un número que no creemos no
se le da a un modelo cuya única defensa es no poder afirmar de más.** Si entrara, el
modelo escribiría «causa en sentido de Granger con p = 0,001» y la culpa no sería suya.

Los caveats de estos dossiers son estructurales, no de cortesía: que Cholesky es un
supuesto del analista y no algo que los datos identifiquen; que el bootstrap de
percentiles sin corrección de sesgo da un piso de la incertidumbre y no un techo; que el
shock es de un desvío estándar y no de una magnitud elegida; que el sistema va en
log-diferencias porque el IPC es I(2) y el TC I(1); y que la muestra mensual **poolea
regímenes** (2018-19, 2023-24) sin que se haya testeado estabilidad de parámetros.

### El signo tipográfico

Un detalle de parseo que era un falso positivo garantizado: el modelo escribe con
tipografía correcta y usa el menos matemático **U+2212** (`−`), que no es el guion ASCII.
Sin normalizarlo, «−0,80» se leía como +0,80 y **toda IRF negativa legítima salía
marcada**. Se normaliza solo ese carácter; la raya (`–`, U+2013) queda afuera a propósito,
porque separa rangos («2017–2026») y convertirla en signo inventaría un «-2026».

El bug ya afectaba a `dossier_serie` —cualquier variación interanual negativa— y estaba
latente desde el principio.

## 7. Qué queda pendiente

- **Estabilidad de parámetros.** El caveat de regímenes pooleados dice la verdad, pero
  decirla no es testearla: falta Chow / ventanas móviles sobre el VAR mensual, que es el
  único de los dos que se estima sin partir por régimen.
- **Caché compartido.** Hoy vive en el disco del contenedor: en Streamlit Cloud se pierde
  con cada reinicio, así que la primera visita tras dormir paga la redacción de nuevo.
- **Costo observado.** No se registra el gasto por lectura; con el caché las llamadas son
  pocas, pero no están medidas.

---

## Dónde sigue esto

- **El menos tipográfico U+2212**, que marcaba como inventada toda IRF negativa legítima, con
  su clase de error: [trampas de datos](notas/trampas-de-datos.md).
- **Por qué no hay chat y por qué el determinismo no viene de bajar la temperatura**:
  [decisiones descartadas](notas/decisiones-descartadas.md).
- **Qué queda pendiente de la capa** —el caché compartido, el costo sin medir—:
  [preguntas abiertas](notas/preguntas-abiertas.md).
- Los dossiers econométricos redactan sobre los resultados de
  [hallazgos econométricos](hallazgos_econometricos.md); el de espejo, sobre
  [comercio espejo](comercio_espejo.md).
