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

### Pendiente
- **Un envío real de punta a punta** (página → formulario → «Create») para guardar el cuerpo que escribe GitHub como fixture del paso 4. Lo hace Aday, porque la extensión de Chrome sigue bloqueada.
