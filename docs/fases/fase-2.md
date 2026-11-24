# Fase 2 — Prioridades de Sofía

> **Borrador del 2026-11-18 (SCOPE v213): la fase sigue abierta.** Se cierra con el visto bueno de Sofía y este documento terminado (SCOPE §7). Lo que depende de ella aparece como *pendiente (Sofía)*. Las cifras que aún no existen aparecen como *pendiente*, y ninguna se ha estimado para rellenar el hueco. El estudio previo de Neuro Atlas está aparte, en [`fase-2-atlas-ux.md`](fase-2-atlas-ux.md), y la medida de Neuro Lab en [`fase-2-neuro-lab.md`](fase-2-neuro-lab.md).

## Estado del cierre

| Requisito | Estado |
|---|---|
| Neuro Atlas: visor, fichas de las 12 parejas, estudios por pareja, técnica ↔ región, orden provisional | hecho en `main` (v160–v207) |
| Neuro Atlas: textos «qué es y qué hace» de cada pareja | código hecho (v212); borradores en Groq: 10 de 12 (v216, v220, v222); revisión: *pendiente (Sofía)*, en su cola desde el 2026-11-25 |
| Neuro Atlas: introducción humano–rata | código y fuentes hechos (v221; tres secciones de Wikipedia, porque ningún artículo compara los dos cerebros); borrador en Groq: hecho (v222); revisión: *pendiente (Sofía)*, la primera de los textos de Atlas desde el 2026-11-25; filas 11 y 15 de su hoja |
| Neuro Atlas: tabla de búsquedas por región, grados de equivalencia y enfermedades | *pendiente (Sofía)*: filas 10, 13, 16 y 18 |
| Neuro Lab: fichas con estudios y textos | hecho (v201–v228); 16 tarjetas en su cola desde el 2026-11-19; 4 «Límites» sin fuente (fila 40) y 2 que suspendieron (fiber photometry y perfusión, v232) |
| Neuro Glossary | en la web con sus 7 términos (v183); *pendiente (Sofía)*: los 24 términos de su cola y `regions.csv` |
| Visto bueno de Sofía | *pendiente (Sofía)* |

## Para qué servía esta fase

Construir las tres secciones que Sofía puso primero en su revisión de la propuesta: **Neuro Atlas** (los dos cerebros en 3D y sus parejas rata ↔ humano), **Neuro Lab** (qué permite ver cada técnica y sus límites) y **Neuro Glossary**. Todas tienen la misma restricción: el contenido científico lo valida ella, en cerca de una hora al día y sin terminal. Por eso casi todo lo de esta fase tiene dos mitades: una **propuesta automática y marcada como tal**, y **su cola de revisión**, que es la que la convierte en contenido.

Empezó en paralelo a la Fase 1 (v154). Desde la v159, cada parte se fusiona en `main` en cuanto está lista, en lugar de esperar los 14 días de autonomía de la Fase 1.

## Lo que se construyó

| Bloque | Versiones | Qué hace |
|---|---|---|
| Estudio de UX de Neuro Atlas | v155–v158 | Decisiones UX-1–UX-6 y maquetas para Sofía antes de escribir el visor |
| Visor y página de Neuro Atlas | v160–v176, v185 | `syn atlas build` (datos del visor), página con buscador, visor Niivue con los dos cerebros, translucidez y cortes; arreglos en móvil |
| Fichas de región | v166, v188–v194, v207 | 43 fichas por idioma (12 de la rata y 31 humanas) con los estudios de su pareja en animales y en humanos, por MeSH y por texto |
| Neuro Glossary | v177–v184, v199, v203 | Página A–Z, fuentes de Wikipedia, cola de Sofía, ventanita de siglas en el visor, el inglés tras sus correcciones solo en español y los términos marcados en los resúmenes |
| Neuro Lab | v201–v206, v208–v210 | Medida de MeSH por técnica, fichas con estudios, tarjetas de búsquedas en su cola, técnica ↔ región y textos desde Wikipedia |
| Cadena común de textos fijos | v211–v212, v221 | `narrative/wikidraft.py`, que comparten Neuro Lab, las regiones y la introducción (esta, con tres fuentes: cada hecho guarda la suya y cada frase cita las de sus hechos) |

## Lo que se decidió y por qué

### La propuesta automática se marca, no se esconde
Las tablas pareja → MeSH (v188), técnica → MeSH (v202) y técnica ↔ región (v206) se publican con la etiqueta «propuesta» hasta que Sofía las revisa. Esconderlas dejaría las fichas vacías durante semanas. Publicarlas sin marca haría pasar por validado lo que no lo está. Su aprobación en la cola quita la etiqueta sin que nadie toque un archivo (v192).

### Su hora al día es un presupuesto
Cada tipo de tarjeta entra en su cola en una fecha y con un cupo: el glosario, 8 al día; los textos de Lab, 3 al día laborable y 1 el fin de semana desde el 19-11; los de las regiones, igual desde el 25-11, justo cuando acaban los de Lab. Es la misma idea que el cupo de Groq en la Fase 1: no se reparte por orden de llegada, sino por lo que cabe.

### Los textos fijos salen de Wikipedia, citada en su revisión
Las fichas necesitan textos estables («qué permite ver», «qué es y qué hace»), no resúmenes de estudios. La fuente es la entradilla de Wikipedia en inglés, guardada con su número de revisión (`syn lab sources`, `syn atlas sources`, v205). Así cada frase se puede comprobar contra un texto fijo, y si el artículo cambia, el borrador sale de su cola hasta redactarlo otra vez. La licencia CC BY-SA 4.0 se muestra en cada ficha.

### Los hechos clínicos nunca se escriben en las regiones (v212)
El modelo marca cada hecho como anatomía, función, clínico u otro. Los clínicos se descartan antes de redactar: las enfermedades van por la lista que revisa Sofía (fila 16), y la web nunca habla de tratamientos.

### Generalizar la cadena en lugar de copiarla (v211)
Neuro Lab, las regiones y la introducción usan la misma cadena (hechos con cita → EN → ES → comprobaciones). Con una tercera copia, un arreglo en una se olvidaría en las otras. La prueba de que el refactor no rompió nada: los 13 elementos de la cola de Lab salen idénticos, con el mismo hash, antes y después.

### El trabajo no espera a GitHub Actions (v195)
El run programado empieza entre 9 y 11 horas tarde. Antes de cada push se corre `scripts/ci_local.sh`, que hace lo mismo que la CI y además `syn site --check` sobre una copia reconstruida de la rama `data`.

### El español de los textos fijos tiene su propio prompt (v232)
Al reintentar, los mismos textos volvían a suspender por lo mismo: causalidad añadida, «may» como «puede» y un nombre de animal inventado. El prompt de español de los resúmenes diarios (`adapt_es`) no se podía cambiar, porque su versión forma parte de la clave de caché de cada resumen y cambiarla los reescribiría todos con la Fase 1 abierta. Por eso los textos fijos usan `wiki_adapt_es`, con esas reglas. `syn lab write --failed-only` vuelve a pedir solo la sección que suspendió, sin tocar la que ya está en su cola, y la prueba de que no se tocó es el hash de sus 27 tarjetas.

### `pipeline.yml` no se toca con la Fase 1 abierta
Su reloj de 14 días mide si el pipeline corre solo. Por eso los comandos nuevos de esta fase (`syn lab write`, `syn atlas write`) se lanzan a mano y nunca en el pipeline, y `syn figures` y `syn titles` esperan al cierre de la Fase 1 (SCOPE §10).

## Cifras

| Medida | Valor | Fuente |
|---|---|---|
| Neuro Atlas en el móvil simulado | ver la medida del paso 4 | v164, [`fase-2-atlas-ux.md`](fase-2-atlas-ux.md) |
| Regla del resumen por pareja (2 menciones) frente a MeSH | precisión 0,66 y recall 0,55 | v194–v195 |
| Neuro Lab: estudios con MeSH entre los de neurociencia | 2081 de 5059 | v201 |
| Fuentes de Wikipedia | Lab: 10 en inglés y 8 en español; Atlas: las 12 parejas en los dos idiomas | v205 |
| Borradores de Lab (Groq) | «qué permite ver» en 11 de 11 (trazado viral, v226, y perfusión desde una sección, v228); «límites» en 5 de 11 (con optogenética, v217); 16 tarjetas en su cola | v209, v217, v226, v228 |
| Borradores de las regiones (Groq) | 10 de 12 parejas; 2 huecos (hipocampo y quiasma óptico), que suspenden el español | v216, v220, v222 |
| Introducción humano–rata (Groq) | 17 hechos verificados de 3 secciones, ninguno clínico; 4 frases | v222 |
| Medida B de Neuro Lab (run del 18-11, con resúmenes) | western blot 2 → 20, inmunofluorescencia 0 → 15; confocal, trazado viral y perfusión siguen casi vacías | v217, [`fase-2-neuro-lab.md`](fase-2-neuro-lab.md) |
| Textos aprobados por Sofía (Lab, Atlas y glosario) | *pendiente (Sofía)* | `review/decisions.jsonl` |

## Conceptos, desde cero
- **Propuesta frente a contenido:** una tabla generada por reglas (MeSH, texto, estudios en común) es una hipótesis. Se convierte en contenido cuando alguien con criterio la revisa, y la web distingue las dos cosas.
- **Fuente fijada por revisión:** en Wikipedia, cada versión de un artículo tiene un número. Citar el número, y no solo el título, permite comprobar mañana que una frase decía lo que decía la fuente.
- **Hash del contenido:** cada tarjeta de su cola lleva un `content_sha256`. Su decisión vale para esa versión exacta: si el texto cambia, vuelve a su cola.
- **Datos de atlas que no se mezclan:** Waxholm (CC BY 4.0) y Julich-Brain (CC BY-NC-SA 4.0) van por separado, también en las fichas. Una pareja enlaza dos fichas, no fusiona sus datos.

## Cómo se comprueba
- `uv run pytest` sin red: `FakeLLM` que responde según el esquema pedido, entradillas escritas para el test y `httpx.MockTransport`.
- `syn site --check` con fixtures y sobre los datos reales en `ci_local.sh`: ninguna ficha publica un texto sin aprobación registrada.
- Los recuentos de estudios por técnica y por pareja salen en el log de `syn site` de cada run.
- Revisión visual en Chrome y en el móvil de Aday (S23) del visor.

## Qué salió mal (y qué se aprendió)
- **Groq devolvió JSON mal formado** (v209) y el error paró toda la ejecución de Lab. Ahora un `LLMOutputError` deja esa técnica como `model_error` y se sigue con las demás, y el prompt escribe la forma del JSON. *Lección:* un lote no debe depender de que salga bien cada llamada.
- **MeSH con etiqueta de idioma** (v201, [`fase-2-neuro-lab.md`](fase-2-neuro-lab.md)): los números de árbol de MeSH llevan idioma (`"…"@en`), así que `?tn = "A08.186.211"` nunca se cumplía y `atlas.studies.fetch` perdía el descriptor del propio árbol. Arreglado con `STR(?tn)`. *Lección:* probar la consulta con un descriptor conocido antes de fiarse de un «ninguno».
- **`syn` no lee `.env`** (v209, igual que `syn judge` en la Fase 1). Se lanza con `uv run --env-file .env syn …`.
- **El test de frescura en `ci_local`** fallaba con un almacén construido con la fecha de hoy sobre datos de ayer. Se reconstruye con `syn build --as-of <fecha de los datos>`.
- **Un `Retry-After` de horas colgó la ingesta** (v186) y **`syn news group` llegó a su tiempo máximo** (v187). Los dos se arreglaron haciendo que el comando pare solo y deje lo pendiente para el día siguiente, en lugar de alargar el tiempo.
- **Las entradillas no hablan de límites.** De las 10 técnicas, 5 no tenían ningún hecho de «límites» (v209). Tres tienen una sección de limitaciones en Wikipedia, pero al leerlas solo la de optogenética trata de límites: la de western blot es una guía para resolver fallos y la de quimiogenética habla sobre todo de enfermedades en humanos. Solo optogenética usa su sección (v215); de las otras cuatro se le pregunta a Sofía (fila 40). *Lección:* medir una fuente es leerla, no solo contar si existe.
- **Un guion no separable rompió el JSON de Groq** (v220). La entradilla de la corteza motora (la pareja de la superficie) era la única con «‑» (U+2011), y era la única en la que el modelo no daba JSON válido, dos veces y al instante. Ahora la cadena convierte ese carácter en «-» antes de dárselo al modelo y a las comprobaciones, y al tercer intento salió el borrador. *Lección:* cuando una sola entrada falla siempre, busca qué tiene distinto antes de reintentar.
- **Sus tarjetas no se entendían** (hoja, 24-11): contestó «No entiendo» al glosario, a las búsquedas por región y a los grados, y al 14b respondió con temas en lugar de tipos. Las instrucciones explicaban de dónde salía cada cosa, pero no qué tenía que hacer ella. Ahora cada grupo dice «Qué haces» con un ejemplo (v236). *Lección:* una instrucción para alguien no técnico empieza por la acción que se le pide, no por cómo funciona el programa.
- *Pendiente: lo que salga de su revisión.*

## Sus respuestas a la hoja (2026-11-24, pegadas por Aday)
- **Cerradas:** el bloque «Hoy» no sube; las siglas van en inglés y los nombres en español salen de Wikipedia; bastan los 3 grados; 5 estudios recientes por región; da por buenos los nombres de las familias y el enlace de las regiones con el glosario; sin Wikipedia en español, la inglesa; quiere revisar las enfermedades antes de publicarlas; revisará la tinción con el visor nuevo.
- **Hechas sin LLM** (opciones de Aday): el glosario en la web sin paréntesis anidados y con punto final (v235), y las instrucciones de sus tarjetas (v236). En curso: sus Clásicos, el orden de regiones con la zona incerta, «ir a la pareja», la nota de lo que falta en el humano y los dos cerebros al entrar en el ordenador.
- **Sus 11 temas** para Neuro News (propuesta, no cambia la Fase 1; Aday: opción recomendada): neurobiología celular y molecular; circuitos neuronales y neurofisiología; cognición y comportamiento; neurodegeneración; salud mental y neuropsiquiatría; adicciones y neurofarmacología; neurodesarrollo y envejecimiento; neuroinmunología; neuroendocrinología y metabolismo; neurotecnología y neurociencia computacional; neurociencia clínica y traslacional. Son un eje distinto del tipo del 14b (de qué trata la noticia, no qué clase de noticia es) y podrían sustituir a los temas MeSH como filtro. Se planifica después del cierre de la Fase 1.
- **Para planificar con LLM o fuentes nuevas:** los «Límites» de las 4 técnicas con sus 4 revisiones de PMC (antes, comprobar su licencia); «evite su muerte» en perfusión; una introducción de Atlas más amplia (dio 17 diferencias) sin tapar el cerebro; y Neuro Lab en tres partes (descripción, protocolo con imágenes y artículos recientes), sin relación forzada entre región y técnica.

## Cómo defenderlo en una entrevista
- «Con un revisor experto y una hora al día, el cuello de botella es su tiempo, no el código. Diseñé su cola con cupos y fechas por tipo, y todo lo automático se publica marcado como propuesta hasta que ella lo aprueba.»
- «Los textos fijos citan una revisión concreta de Wikipedia. Así son comprobables, y si la fuente cambia, el texto vuelve a revisión solo.»
- «En las regiones, el modelo clasifica cada hecho y descarto los clínicos antes de redactar. Prefiero un texto más corto a uno con contenido de salud sin revisar.»
- «Generalicé la cadena cuando apareció el tercer uso, no antes. Probé el refactor con algo comprobable: la misma cola, con el mismo hash.»

## Lo que queda
- *Pendiente (Sofía):* su revisión de los textos de Lab y de Atlas, del glosario, de las búsquedas por región y por técnica, de los grados de equivalencia y de las enfermedades.
- Los «Límites» de confocal, electrofisiología, western blot y quimiogenética: Sofía dio una revisión de PMC para cada una (24-11); falta comprobar su licencia y redactarlos (LLM, con OK de Aday). Los de optogenética salieron de su sección (v217).
- El reintento de los 4 textos que suspendieron (hipocampo, quiasma óptico, «Límites» de fiber photometry y de perfusión) con los prompts de la v232: necesita el OK de Aday.
- La revisión de la introducción humano–rata, *pendiente (Sofía)*.
