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

## 6. Qué queda pendiente

- **Dossier econométrico.** Redactar sobre el VAR, el pass-through y el nowcast exige
  llevar al dossier los supuestos de identificación (el orden de Cholesky) y el ancho de
  las bandas, no solo los puntos estimados. Ver `hallazgos_econometricos.md` §5.
- **Caché compartido.** Hoy vive en el disco del contenedor: en Streamlit Cloud se pierde
  con cada reinicio, así que la primera visita tras dormir paga la redacción de nuevo.
- **Costo observado.** No se registra el gasto por lectura; con el caché las llamadas son
  pocas, pero no están medidas.
