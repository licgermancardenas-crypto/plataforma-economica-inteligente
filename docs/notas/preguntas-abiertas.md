# Preguntas abiertas

Lo pendiente, con **qué haría falta para cerrarlo**. Ordenado por lo que más cambiaría las
conclusiones actuales, no por dificultad.

---

## 1. El pass-through puede haber cambiado y no lo podemos ver

**Estado:** limitación de muestra, no de método.

El sup-Wald no rechaza estabilidad en ninguna ecuación, pero su potencia contra un quiebre en
un coeficiente aislado es del 12% con quince errores estándar. Se descarta un cambio de
régimen generalizado; **no** se descarta un cambio en el pass-through, que es justo el
parámetro del que dependen las IRF publicadas.

**Qué haría falta:** el tramo TC → precios en frecuencia mayor a la mensual. Con IPC de alta
frecuencia (relevamientos semanales de precios, o un índice diario de alimentos) la muestra
permitiría partir por régimen como ya hace el VAR diario, en vez de testear si hace falta
partirla. No hay test mejor: hay que conseguir más datos.

Ver [`hallazgos_econometricos.md`](../hallazgos_econometricos.md) §7.

---

## 2. La discrepancia espejo no tiene contrafáctico

**Estado:** el resultado está, la identificación no.

El contraste contra la brecha da β = +0,059 en el canal exportador (p = 0,025 por bootstrap) y
un cero limpio en el importador. Pero es una **asociación en panel con efectos fijos**, no una
identificación causal: los años de brecha alta en Argentina son también años de crisis,
controles y recesión.

Además, de las cinco fuentes de discrepancia lícita solo se corrige una (flete). Quedan sin
corregir reexportaciones vía terceros países, desfases de timing, clasificación distinta de
cada lado y origen contra procedencia — y cualquiera de esas puede correlacionar con el ciclo.

**Qué haría falta:** el modelo de gravedad de UNU-WIDER, que estima la discrepancia «normal»
de cada par país-producto y deja como residuo la anómala. Es el paso caro: exige datos a nivel
HS de 6 dígitos, que con el preview gratuito de Comtrade no entran (techo de 500 registros).

---

## 3. El generador sintético no está validado contra nada

**Estado:** por construcción, y no tiene arreglo dentro del propio simulador.

Un detector entrenado sobre `platec/firmas_sinteticas.py` encuentra las maniobras que
nosotros mismos inyectamos. Sirve para comparar métodos entre sí, medir potencia y armar el
pipeline; **no** como evidencia sobre el lavado real en Argentina.

**Qué haría falta:** una muestra etiquetada real, que en la práctica significa un convenio
con la UIF o con un organismo que tenga acceso a reportes de operación sospechosa. Sin eso,
la validación externa posible es indirecta: comprobar que el agregado sintético reproduce
momentos observados (ya se hace con el β del canal exportador) y que los detectores
calibrados acá se comportan de forma parecida sobre datos públicos de otras jurisdicciones.

---

## 4. El pass-through usa tipo de cambio nominal

**Estado:** aproximación declarada.

Para un tipo de cambio real bilateral falta CPI externo (FRED). Deflactar solo por precios
locales, como se hace hoy, es aproximado.

**Qué haría falta:** una fuente más en el catálogo (FRED tiene API pública y estable). Es de
las pendientes más baratas.

---

## 5. La tabla de Granger mensual usa un criterio que el proyecto no cree

**Estado:** deuda técnica con consecuencia metodológica.

Sigue mostrándose con «p mínimo sobre 6 rezagos», que no es un p-valor sino el mejor de seis
pruebas sin corregir por comparaciones múltiples. Fue reauditada con el test conjunto y las
conclusiones no cambian, pero **conviven dos criterios en el mismo proyecto**.

**Qué haría falta:** migrar la tabla a `granger_sistema()`. Cerrarlo además habilita a meter
Granger en el dossier del LLM, de donde hoy está excluido a propósito.

---

## 6. El IPC resulta I(2)

**Estado:** decidido para el corto plazo, abierto para el largo.

Hay que diferenciar dos veces para estacionarizar: no solo el nivel de precios tiene
tendencia, también la *tasa* de inflación. Es típico de regímenes de inflación alta. La
consecuencia directa es que **no se puede cointegrar IPC (I(2)) con TC (I(1))**, y por eso el
sistema va en log-diferencias: hay dinámica de corto plazo, no hay relación de largo plazo
estimada.

**Qué haría falta para un modelo de largo plazo:** evaluar el sistema en la tasa de inflación,
o un VECM I(2).

---

## 7. El caché del narrador se pierde en cada reinicio

**Estado:** costo, no rigor.

Vive en el disco del contenedor. En Streamlit Cloud el contenedor es efímero, así que la
primera visita después de que la app duerme paga la redacción de nuevo.

Tampoco se registra el gasto por lectura: con el caché las llamadas son pocas, pero no están
medidas.

---

## 8. El job diario commitea aunque no haya datos nuevos

**Estado:** ruido en el historial.

`snapshot_meta.json` lleva un campo `generado` con la hora actual, y el chequeo de diff del
workflow lo incluye — así que siempre difiere y siempre commitea. Por eso hay commits los
fines de semana y a veces dos el mismo día.

**Qué haría falta:** sacar `snapshot_meta.json` del chequeo de diff y escribirlo solo cuando
el `.csv.gz` cambió. El `.csv.gz` ya es determinista, así que el chequeo sobre él solo es
confiable.

---

## 9. Falta la deuda pública

**Estado:** bloqueado por la fuente.

El Ministerio de Economía la publica en informes y planillas, no como serie en la API. Lo más
cercano disponible es `intereses_netos` (2016+), que mide la carga del servicio, no el stock.

**Qué haría falta:** parsear las planillas de la Secretaría de Finanzas. Otras ausencias por
el mismo motivo: balanza de pagos, deuda externa privada, y gasto público desagregado antes
de 2016.
