# Decisiones descartadas

Lo que se evaluó y no se hizo, con el motivo. Existe para no reabrir discusiones cerradas y,
sobre todo, para que la decisión se pueda **revisar con su fundamento a la vista** si cambian
las condiciones.

Cada entrada dice qué haría falta para dar la decisión vuelta.

---

## `comtradeapicall` como dependencia

**Se usa `requests` contra el endpoint público.**

El paquete oficial envuelve el mismo REST. Sus funciones que agregan valor de verdad
—`getBilateralData`, `getFinalData`— **exigen subscription key de pago**. Lo que queda gratis
es `/public/v1/preview`, que son treinta líneas. Sumar una dependencia que además arrastra sus
propias versiones de pandas al build de Streamlit Cloud no se paga, y los otros tres fetchers
del proyecto están escritos igual.

**Se revisaría si:** se contrata la key, o si el preview deja de servir (hoy: un período por
llamada, techo de 500 registros).

---

## Estimar el VAR mensual por régimen

**Se testea estabilidad en vez de partir la muestra.**

Son 112 meses y un VAR de cinco variables con dos rezagos tiene once parámetros por ecuación.
Los cortes disponibles dejan 30/82, 34/78 y 82/30. Con 30 observaciones y once parámetros no
se estima nada creíble, y menos una IRF con bandas por bootstrap.

Estimar por régimen es lo que la frecuencia diaria permite —3.264 días— y la mensual no.

**Se revisaría si:** se consigue el tramo TC → precios en frecuencia mayor a la mensual. Ver
[preguntas abiertas](preguntas-abiertas.md).

---

## El AML canónico (AMLSim, Elliptic, Jube)

**Se fue por flujos financieros ilícitos vía mala facturación.**

Los repos de anti-lavado resuelven un problema micro-transaccional —grafos de contrapartes,
desbalance de 1 en 10.000— que no es el de esta plataforma, y sobre todo **entrenan sobre
datos que no existen**: los reportes de operación sospechosa son confidenciales por ley en
toda jurisdicción, así que se usa o un simulador (`IBM/AMLSim`, donde uno entrena sobre
patrones que definió uno mismo) o cripto (`Elliptic`, que no es economía real).

`jube-home/aml-fraud-transaction-monitoring` además es **AGPL-3.0**, licencia contagiosa por
red: integrarlo y servir el dashboard público obligaría a liberar todo bajo AGPL.

La rama que sí sirvió es la macroeconométrica, porque la plataforma **ya tenía media ecuación
construida**: exportaciones e importaciones del INDEC desde 1992 y la brecha cambiaria diaria.

**Se revisaría si:** aparece acceso a datos transaccionales reales, lo que en la práctica
significa un convenio institucional.

---

## El factor CIF/FOB fijo del 10%

**Se estima por país declarante.**

Es el supuesto estándar de la literatura y en el agregado no está mal —la mediana calculada
sobre los datos da +7,5%— pero por socio va de **+3,9% en Brasil a +12,5% en Australia**.
Aplicarle 10% a Brasil sobrecorrige seis puntos y **da vuelta el signo** de la discrepancia:
convierte una subfacturación en un superávit espejo que no existe.

**Se revisaría si:** se quisiera comparabilidad estricta con los números publicados por GFI.
Ahí conviene reportar las dos series, no cambiar el criterio.

---

## El «p mínimo sobre 6 rezagos» de Granger en el dossier del LLM

**No entra.**

Ese mínimo no es un p-valor: es el mejor de seis pruebas, sin corregir por comparaciones
múltiples. El proyecto ya lo tiene marcado como criterio a migrar a `granger_sistema()`.

Un número que no creemos no se le da a un modelo cuya única defensa es no poder afirmar de
más: si entrara, el modelo escribiría «causa en sentido de Granger con p = 0,001» y la culpa
no sería suya.

**Se revisaría si:** se completa la migración a `granger_sistema()`.

---

## Los coeficientes del ElasticNet en el dossier del LLM

**No entran.**

Están sin estandarizar, así que sus magnitudes no son comparables entre variables de escalas
distintas y no sostienen la frase «tal variable pesa más» que invitarían a escribir. A
diferencia del caso de Granger no son *inválidos*, solo no comparables — pero en una lectura
de 3 a 5 oraciones agregan poco y prestan a error.

**Se revisaría si:** se estandarizan los features.

---

## Bajar la temperatura del LLM para tener determinismo

**Se cachea por hash del dossier.**

Los modelos actuales de la familia Opus **rechazan `temperature` con un 400**. Y aun cuando
existía, temperatura 0 nunca garantizó determinismo real.

El caché por `sha256(versión del prompt + modelo + dossier + pregunta)` sí lo da: mismos
datos, mismo texto, hasta que los datos cambien.

---

## Un chat sobre datos macro en la capa de IA

**No hay chat, ni preguntas libres, ni recuperación de documentos.**

Un chat es justamente la forma en que un LLM entra a una herramienta de análisis a responder
de memoria. Acá cada respuesta está anclada a un dossier construido en Python, y cada número
del texto se verifica contra ese dossier antes de mostrarse.

Es una restricción de producto deliberada, no una etapa pendiente.

---

## Vercel / Netlify / GitHub Pages para el deploy

**Streamlit Community Cloud.**

Streamlit es un servidor de larga vida: mantiene un WebSocket abierto y reejecuta el script en
cada interacción. Las plataformas de sitios estáticos responden 404 porque no hay build que
publicar, y sus funciones mueren a los segundos.

Hubo un intento en `plataforma-economica-inteligente.vercel.app` que nunca funcionó. Si el
tema reaparece, la respuesta es esta, no depurar el build.

---

## Un vault de Obsidian separado del repo

**El vault apunta al repo.**

La mayor fortaleza documental del proyecto es que `docs/comercio_espejo.md` y
`platec/comercio_espejo.py` cambian en el mismo commit. Un almacén paralelo rompe eso: el doc
y el código derivan, y en seis meses no se sabe cuál miente. Apuntando Obsidian al repo no hay
migración ni lock-in — son `.md` planos que se siguen leyendo en GitHub.
