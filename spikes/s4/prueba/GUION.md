# S4 · Guion de la prueba con Sofía

Para Aday. Se hace **cuando termine S3** (la elección entre las maquetas B y C va primero). Unos 45 minutos en total, en dos rondas; la segunda puede ser otro día.

**Qué se prueba:** el flujo de revisión entero tal como lo viviría ella: abrir la página, decidir, enviar a GitHub, recibir la respuesta y ver qué vuelve a su cola. **No** se prueba el contenido: la ficha de Neuro Diseases es un texto de prueba.

**Lo que no cambia:** el workflow de recepción sigue sin activar. Sus Issues los procesamos a mano (sección «Entre rondas»), así que no hay que tocar ningún ajuste de GitHub para la prueba.

## Antes (sin Sofía)

1. Regenerar las páginas si ha cambiado algo del spike:
   ```sh
   uv run --group spike-s4 python spikes/s4/prueba/make_queue.py
   uv run --group spike-s4 python spikes/s4/ronda.py --queue spikes/s4/prueba/queue.json \
       --data-dir spikes/s4/prueba/datos --out spikes/s4/prueba/ronda-1
   ```
   (`datos/` aún no existe: la primera ronda sale con todo pendiente, 19 elementos.)
2. Tener a mano los dos archivos de `spikes/s4/prueba/ronda-1/`: `revision.html` y `revision-privada.html`.
3. Imprimir o tener abierta la hoja de observación (al final).

## Con Sofía: la cuenta de GitHub (unos 10 min)

- github.com/signup: correo, contraseña y nombre de usuario. Es gratis y no pide tarjeta.
- Verificar el correo.
- Recomendado: la verificación en dos pasos (app de autenticación o llave de acceso), porque a la cuenta se le dará permiso de revisión.
- Apuntar su nombre de usuario: hace falta para procesar sus Issues.
- **Cerrar la sesión de GitHub al acabar.** El primer envío se hace sin sesión, a propósito: es el caso en que GitHub la manda al login con la URL entera, y queremos ver que el formulario sigue relleno al volver.

## Ronda 1 (unos 25 min)

Mándale los dos archivos (WhatsApp o correo) y que los abra **en el ordenador**. Tú miras y cronometras; no ayudes salvo que se atasque más de un minuto (y apúntalo).

**Se mide la herramienta, no a Sofía.** El tiempo sirve para comprobar el requisito de D5 (menos de 1 h al día). Si cronometrar cada tarea resulta incómodo, basta con la hora de inicio y fin de cada ronda y una nota donde le cueste algo. La ayuda es solo con la página o con GitHub (dónde pulsar, qué hace un botón, el login); **nunca con el contenido**. Si pregunta algo de neurociencia, dile que conteste con su criterio y apunta la duda: una pregunta que genera dudas ya es un resultado.

Página pública, `revision.html`:

| # | Tarea | Qué se observa |
|---|---|---|
| T1 | Leer la introducción | ¿Entiende que las notas son públicas y que puede dejarlo a medias? |
| T2 | Clásicos: elegir los 2 que publicaría | ¿Entiende el máximo? (la tercera casilla se bloquea) |
| T3 | Rata ↔ humano: poner grado a M1, HF y la amígdala; una nota en al menos uno | Lo que conteste es su criterio real: pregúntale después si quiere que cuente |
| T4 | Búsqueda de HF en PubMed: aprobar o corregir los términos | |
| T5 | Glosario: las 6 definiciones (aprobar, corregir o rechazar) | ¿Corrige en el recuadro sin dudar? |
| T6 | Resumen del dolutegravir: corregir la exageración **solo en español** | El inglés lo rehará la IA: ¿le parece bien no tocarlo? |
| T7 | Resumen de los 102 adolescentes: **corregir añadiendo al final** «El seguimiento se repetirá en 2031.» | Es una prueba a propósito: la cifra no está en el texto, así que volverá con un aviso en la ronda 2. Díselo después, no antes |
| T8 | Temas de noticias: ocultar el que crea que sobra (o ninguno) | |
| T9 | Proponer una sigla de su trabajo | |
| T10 | Enviar, **sin sesión iniciada** en GitHub: entrar, comprobar que el recuadro sigue relleno y pulsar «Create» | ¿Cuántas partes salen? ¿El login conserva el formulario? |

Página privada, `revision-privada.html`:

| # | Tarea | Qué se observa |
|---|---|---|
| T11 | Aprobar la ficha de prueba y enviar (ya con sesión) | ¿Entiende por qué esta va en un archivo aparte? |

Opcional, si hay tiempo: abrir `revision.html` en el móvil y hacer una sola tarea. Solo para ver si se puede; la prueba buena es la del ordenador.

## Entre rondas (Aday, unos 5 min)

Por cada Issue que haya abierto (los números salen en GitHub):

```sh
LOGIN=<su usuario>; N=<número del Issue>
COLA=spikes/s4/prueba/queue.json   # ronda 1; en las siguientes, spikes/s4/prueba/ronda-N/queue.json
uv run --group spike-s4 python spikes/s4/event_from_issue.py $N > /tmp/evento-$N.json
uv run --group spike-s4 python spikes/s4/intake.py --event /tmp/evento-$N.json \
    --queue $COLA --data-dir spikes/s4/prueba/datos \
    --reviewer $LOGIN --reply /tmp/respuesta-$N.md \
    --efetch data/cache/s5/pubmed/efetch_20261102.xml   # los abstracts de las fuentes
gh issue comment $N --body-file /tmp/respuesta-$N.md && gh issue close $N
```

Después, la ronda 2:

```sh
uv run --group spike-s4 python spikes/s4/ronda.py --queue spikes/s4/prueba/queue.json \
    --data-dir spikes/s4/prueba/datos --out spikes/s4/prueba/ronda-2
```

Lo esperado (comprobado en `spikes/s4/tests/test_prueba.py`): T7 vuelve con dos avisos, «La cifra 2031 no está en el texto revisado ni en su fuente» y «Frase nueva sin fuente»; lo que contestó en la ronda 1 ya no aparece; lo que dejó sin contestar sigue ahí. Si algo no cuadra, apúntalo y no lo arregles delante de ella.

Las decisiones de la prueba se quedan en `spikes/s4/prueba/datos/`, **no** en la rama `data`: son de prueba. Lo que diga de verdad (grados, glosario, temas) se reutiliza más adelante solo si ella lo confirma.

## Ronda 2 (unos 10 min; puede ser otro día)

Cambiada tras la ronda 1 (2026-11-12, opción A de Aday): Sofía no hizo T6, T7 ni T11, así que nunca vio un aviso ni «Lo mantengo». La ronda 2 recoge esas tareas y una ronda 3 corta prueba el aviso.

Mándale los dos archivos de `ronda-2/`. En la pública solo queda el resumen del dolutegravir; en la privada, la ficha de prueba.

| # | Tarea | Qué se observa |
|---|---|---|
| T12 | Leer la respuesta que dejó el sistema en sus Issues de la ronda 1 | ¿La entiende? ¿Le llegó un correo de GitHub? |
| T6 | Resumen del dolutegravir: corregir la exageración **solo en español** | El inglés lo rehará la IA: ¿le parece bien no tocarlo? |
| T7 | En el mismo resumen, **añadir al final** «El seguimiento se repetirá en 2031.» | Prueba a propósito: la cifra no está en la fuente. Díselo después, no antes |
| T11 | Página privada: aprobar la ficha de prueba y enviar | ¿Entiende por qué va en un archivo aparte? |
| T14 | Enviar las dos | |

Se procesa igual que la ronda 1. Lo esperado: el dolutegravir vuelve con dos avisos, «La cifra 2031 no está en el texto revisado ni en su fuente» y «Frase nueva sin fuente»; la ficha queda aprobada.

## Ronda 3 (unos 5 min)

Solo `ronda-3/revision-ronda-3.html` (se genera como la ronda 2, con `--out spikes/s4/prueba/ronda-3`; desde la ronda 3 cada archivo lleva su ronda en el nombre y en la cabecera, y no se genera la página privada si no tiene nada).

| # | Tarea | Qué se observa |
|---|---|---|
| T13 | El resumen con aviso: corregirlo o elegir «Lo mantengo» con un motivo | ¿Entiende el aviso y la opción? |
| T15 | Enviar | |

Tras procesarla, la cola debe quedar vacía. Después, las preguntas finales.

## Preguntas al final (5 min)

1. ¿Qué te ha costado más?
2. ¿Te ves haciendo esto a diario, en menos de 1 h? ¿Y con 10 elementos? ¿Y con 40, al empezar una fase?
3. ¿Te molesta que tus decisiones y notas se vean en público en GitHub?
4. ¿Te habría resultado más fácil una hoja de cálculo (Google Sheets)?
5. ¿Echas algo en falta?

## Criterios para dar el flujo por bueno (D5)

- Hace T2–T10 con, como mucho, una ayuda.
- La ronda 1 dura 25 minutos o menos.
- Todos sus Issues se leen bien: ninguna decisión rechazada, salvo las que provoca la prueba a propósito.
- El login sin sesión conserva el formulario relleno.
- No le parece mal tener cuenta de GitHub ni que sus decisiones sean públicas.

Si falla el último punto, se prueba la opción D (Google Sheets) antes de cerrar D5.

## Hoja de observación

Fecha: ____  Dispositivo y navegador: ____  Sesión de GitHub iniciada al empezar: sí / no

| # | Tiempo | ¿Dudó? | ¿Ayuda? | Notas |
|---|---|---|---|---|
| T1 | | | | |
| T2 | | | | |
| T3 | | | | |
| T4 | | | | |
| T5 | | | | |
| T6 | | | | |
| T7 | | | | |
| T8 | | | | |
| T9 | | | | |
| T10 | | | | |
| T11 | | | | |
| T12 | | | | |
| T13 | | | | |
| T14 | | | | |

Partes en las que se dividió el envío: ____  Issues abiertos: ____  Decisiones aplicadas / retenidas / rechazadas: ____
