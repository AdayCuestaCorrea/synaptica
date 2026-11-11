# S4 · Resultados

## Paso 3: envío como Issue de GitHub (2026-11-11)

### Relleno del formulario desde la URL
- La plantilla `.github/ISSUE_TEMPLATE/revision.yml` (subida a `main` en `9b095ee`, con la etiqueta `revisión` creada a mano) **se rellena desde la URL**: `issues/new?template=revision.yml&decisiones=…` abre el formulario con el recuadro «Decisiones» escrito y la etiqueta puesta. Probado en Chrome con la sesión de Aday iniciada.

### Longitud máxima de la URL
Medida con `curl` **sin sesión iniciada**, que es el caso que manda: si Sofía no ha entrado en GitHub, GitHub la redirige al login llevando la URL entera, y es esa redirección la que falla.

| Longitud de la URL | Respuesta |
|---|---|
| hasta 6 920 caracteres | 302 (redirige al login) |
| 6 982 – 7 927 | 500 |
| 11 953 o más | 414 (URI demasiado larga) |

- **Límite elegido: `MAX_URL = 6000`** (`review_page.py`), con margen. Con texto en español, cada letra con tilde ocupa 6 caracteres en la URL (`%C3%A1`): 6000 caracteres de URL son unos 4000 de bloque.
- Con la sesión iniciada no se pudo medir: la extensión de Chrome que usa Claude se bloqueó con la URL de 16 000 caracteres («Could not verify this site's safety category») y no se recuperó. Con la sesión iniciada no hay redirección, así que el límite solo puede ser igual o mayor; 6000 vale en los dos casos.

### Qué hace la página con eso
- Reparte las decisiones en **partes** cuya URL quepa en `MAX_URL` («Enviar parte 1 de 2»…). Cada parte es un Issue.
- Una sola decisión que no quepa en ninguna URL (una ficha corregida entera en los dos idiomas) va sola, en una parte **para pegar**: la página copia el bloque al portapapeles y abre el formulario vacío; Sofía pega y pulsa «Create». Es el único caso en que tiene que hacer algo más que pulsar un botón.
- Volumen, medido con las decisiones de las fixtures: una decisión sin texto propio (aprobar, rechazar, grado, elegir, ocultar, proponer una sigla) ocupa entre 240 y 290 caracteres de URL, así que caben unas 20 por Issue; una corrección de un par de frases, unos 430. Un día normal (Clásicos y algún texto) es un solo Issue.

### Envío real de punta a punta
- [Issue #1](https://github.com/AdayCuestaCorrea/synaptica/issues/1), enviado por Aday desde `revision.html` con 3 decisiones (un Clásico, un grado con nota y unos términos aprobados): título `Revisión de Sofía · 2026-11-11 · 1/1`, etiqueta `revisión` y el cuerpo exactamente como lo espera `issue_block.decode` (`### Decisiones` y el bloque en una valla `text`). Las 3 decisiones pasan `check_against` con la cola de las fixtures.
- Guardado como `tests/fixtures/review/issue_opened_1.json`, con la forma del evento `issues: opened` que recibirá el workflow. Cerrado a mano como «not planned».

## Paso 4: recepción (2026-11-11)

`intake.py` lee el evento `issues: opened` y devuelve una de cuatro salidas: *ignored* (otro autor, o no es una apertura), *duplicate* (ese Issue ya está en el registro), *refused* (el bloque no se puede leer: no se aplica nada) o *processed*. En *processed*, cada decisión acaba en uno de tres sitios:

| Destino | Cuándo |
|---|---|
| `decisions.jsonl` (aplicada) | pasa el modelo y `check_against`, y si es una corrección de texto, también las comprobaciones |
| `held.jsonl` (vuelve a su cola) | una corrección de texto con algún aviso; ella la corrige o responde «Lo mantengo» |
| rechazada, con el motivo en la respuesta | no valida, el elemento no existe, el texto cambió (hash), elige Clásicos fuera de los candidatos, un elemento privado llega desde la página pública, o «Lo mantengo» sin aviso que mantener |

- **Quién y cuándo** salen del Issue (`user.login`, `created_at` en UTC, `issue#N`). El autor se compara sin distinguir mayúsculas, y el workflow lo comprueba también antes de ejecutar nada.
- **Comprobaciones de sus correcciones**, con las funciones de `spikes/s5/checks.py`: cifras y nombres que no están ni en el texto revisado (en los dos idiomas) ni en sus fuentes; 8 palabras seguidas copiadas de una fuente; y frases añadidas, que no citan nada. Una frase reescrita en su sitio cuenta como corrección de la original y conserva su cita (ver el paso 6: la primera versión, que comparaba frase a frase con un umbral de similitud de 0,5, retenía una corrección corta y legítima).
- **El juez** entra como una función opcional; sus comentarios van a la respuesta con «no bloquea nada». En los tests es una función falsa, sin red.
- **Respuesta** en español y pública, con los títulos de cada elemento: «Aplicadas: N», qué vuelve a su cola y por qué, qué no se ha aplicado y qué comenta el juez.
- **Idempotente:** el mismo Issue dos veces no añade nada (probado de punta a punta con el Issue #1).
- **Workflow** (`review-intake.yml`, borrador sin activar): solo se ejecuta si el autor es `vars.REVIEWER_LOGIN` y el Issue lleva la etiqueta `revisión`; el cuerpo del Issue nunca entra en un `run:` (evita la inyección de comandos; un test lo vigila); permisos mínimos (`contents` e `issues`); comparte `concurrency` con el pipeline para no pisar la rama `data`; comenta y cierra el Issue.
- **Fuera del paso 4:** de dónde salen los textos de las fuentes en el pipeline (el lead de Wikipedia, el abstract en la caché de la rama `data`) y la llamada real al juez (Groq); son de la Fase 1.

## Paso 5: del registro al estado (2026-11-11)

`apply.py` lee `decisions.jsonl` y `held.jsonl` frente a la cola de borradores del día y responde tres preguntas:

- **Estado de cada elemento.** Los eventos se recorren por orden de fecha (y de Issue). Un evento solo cuenta si nombra el hash de la versión que está en la mesa: el borrador de hoy o la corrección retenida que volvió a su cola. Si el borrador cambia, sus decisiones antiguas dejan de contar y el elemento vuelve a estar pendiente.
- **Si se puede publicar** (`publishable`):
  - una ficha de Neuro Diseases, solo con su aprobación o su corrección de la versión actual, con `reviewed_by` y `reviewed_at`;
  - nada de lo que ella rechazó;
  - ningún texto cuyo inglés esté por rehacer a partir de su español (ninguna página en un solo idioma);
  - lo demás se publica mientras espera, como dice §9: solo Neuro Diseases bloquea.
  - Para un par rata ↔ humano, «publicable» no basta: la vista comparada solo aparece si tiene grado (`state.grade`).
- **La cola de mañana** (`next_queue`): lo que no tiene decisión para su versión actual y sus correcciones retenidas, que vuelven con su texto, el aviso y el borrador original (`base`).

Detalles:
- **Correcciones:** cada frase suya conserva las citas de la frase revisada a la que corrige (`intake.align`, la misma regla que las comprobaciones); una frase añadida no cita nada. El idioma que no tocó se queda como estaba hasta que se rehaga.
- **«Lo mantengo»** solo cuenta si nombra el hash de la corrección retenida que está en la mesa; guarda su motivo.
- **Una nueva corrección sobre un texto retenido** se comprueba contra el borrador original, no contra su texto anterior: una cifra que ella añadió no pasa a ser «conocida» (nuevo campo `base` en `ReviewItem`, fuera del hash, y la recepción lo usa).
- **Grados:** se guarda el historial completo (grado, nota, quién, cuándo y si era la versión actual del par), también los de versiones antiguas; el grado vigente solo cuenta para la versión actual.
- **Siglas propuestas:** `proposals` las devuelve para el paso de redacción del glosario (Fase 2).
- Probado de punta a punta: el Issue #1 pasa por la recepción, se escribe en disco y `apply` lee el grado y su nota.

## Paso 6: prueba con Sofía preparada (2026-11-11)

- **Guion:** [`prueba/GUION.md`](../prueba/GUION.md), para Aday. Dos rondas (unos 25 y 5 minutos) más la creación de su cuenta de GitHub. Catorce tareas cronometradas, el primer envío sin sesión iniciada (el caso de la redirección al login), preguntas finales, criterios para dar el flujo por bueno y hoja de observación. Si no le convence tener cuenta o que sus decisiones sean públicas, se prueba la opción D antes de cerrar D5.
- **Cola de prueba:** `prueba/queue.json`, 19 elementos (la de las fixtures, más dos resúmenes de S5 y cuatro siglas de la propuesta); páginas de la ronda 1 en `prueba/ronda-1/`.
- **Sin activar nada en GitHub:** sus Issues se procesan a mano con `event_from_issue.py` (lee el Issue con `gh`) e `intake.py`; `ronda.py` aplica el registro y genera las páginas de la ronda siguiente. Las decisiones de la prueba quedan en `prueba/datos/`, no en la rama `data`.
- **Ensayo en seco** (`tests/test_prueba.py`): una ronda 1 simulada (corregir la exageración del dolutegravir solo en español, la frase de prueba de T7 y aprobar GABA) da justo lo que promete el guion: la corrección se aplica con el inglés por rehacer, GABA sale de la cola y T7 vuelve con sus dos avisos.
- **Fallo encontrado por el ensayo y corregido:** la corrección de la exageración, más corta que la frase original, se quedaba por debajo de 0,5 de similitud y se retenía como «frase nueva sin fuente». Ahora las frases se alinean como secuencia (`intake.align`): una frase reescrita en su sitio corrige a la original y conserva su cita; solo las añadidas cuentan como nuevas. Las comprobaciones de cifras, nombres y copia siguen aplicándose a todas.

