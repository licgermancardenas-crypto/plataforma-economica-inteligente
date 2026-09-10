# Bitácora de investigación

Esta carpeta es la capa que faltaba. `docs/` documenta **lo que el código hace**; acá va
**lo que se aprendió haciéndolo**: la literatura que sostiene cada decisión, los caminos que
se descartaron y por qué, las trampas de datos que costaron horas, y lo que quedó abierto.

Hasta ahora eso vivía mitad en `docs/`, mitad en mensajes de commit y mitad en la cabeza.
Los mensajes de commit son un buen lugar para *registrar* algo y un pésimo lugar para
*encontrarlo* seis meses después.

## Las cuatro notas

| Nota | Qué guarda |
|---|---|
| [Literatura](literatura.md) | Los papers y métodos que sostienen cada decisión, con qué se tomó de cada uno |
| [Decisiones descartadas](decisiones-descartadas.md) | Lo que se evaluó y no se hizo, con el motivo. Evita reabrir discusiones cerradas |
| [Trampas de datos](trampas-de-datos.md) | Los errores silenciosos de las fuentes. La nota más cara de reconstruir si se pierde |
| [Preguntas abiertas](preguntas-abiertas.md) | Lo pendiente, con qué haría falta para cerrarlo |

## Convenciones

**Las notas se versionan con el código.** Es la razón de que vivan en `docs/notas/` y no en
un vault aparte: la fortaleza documental de este proyecto es que `docs/comercio_espejo.md` y
`platec/comercio_espejo.py` cambian en el mismo commit. Un almacén paralelo rompe eso y en
seis meses no se sabe cuál miente.

**Links relativos de markdown, no `[[wikilinks]]`.** Obsidian sigue los dos; GitHub solo el
primero, y muestra el segundo como texto roto. Como estos archivos se leen en los dos lados,
gana el que funciona en ambos.

**Nada de plugins que generen contenido.** Dataview y compañía producen texto que no existe
fuera de Obsidian: quien abra el repo en GitHub vería un bloque de código en vez de una
tabla. Si hace falta una tabla, se escribe.

**Una nota no repite lo que ya dice `docs/`.** Si el detalle metodológico está en
`comercio_espejo.md`, acá va el link y la parte que no cabe ahí: de dónde salió el criterio,
qué se probó antes, qué quedó sin resolver.

## Cómo abrirlo en Obsidian

`Open folder as vault` → apuntar a la **raíz del repo** (o a `docs/` si preferís no ver el
código). No hay que importar ni copiar nada: Obsidian lee los `.md` que ya están. La
configuración local del programa queda en `.obsidian/`, que está en el `.gitignore`.
