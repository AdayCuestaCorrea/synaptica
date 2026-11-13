# Fase 1 — La base

> **Borrador: la fase sigue abierta.** Se cierra con 14 días seguidos de ejecución autónoma sin intervención, el visto bueno de Sofía y este documento terminado (SCOPE §7). Las cifras que todavía no existen aparecen como *pendiente*; ninguna está estimada para rellenar.

## Estado del cierre

| Requisito | Estado |
|---|---|
| Días seguidos sin intervención | **0 / 14**, desde la ejecución programada del 2026-11-14 |
| Visto bueno de Sofía | pendiente |
| 14b · ~100 titulares etiquetados por Sofía: macro F1 del clasificador frente al baseline y validación del juez | pendiente (Sofía) |
| 24b · Primera elección de Clásicos | pendiente (Sofía) |
| 15 · Precisión y recall de la agrupación con un LLM real | pendiente: primera ejecución con Groq |
| 20 · Juicio de los 101 estudios de la carga que quedaron pendientes | pendiente: ejecución programada del 2026-11-14 |
| Retractaciones que solo conoce Retraction Watch (casilla de ingesta) | pendiente |
| 23b · Figuras de PMC | hecho en la rama `fase-1-figuras-titulos` (v125–v128: Pillow, `syn figures`, dbt, web y pipeline); se fusiona después del 2026-11-17. Cobertura medida: 25 de 200 estudios de Última hora con figura (solo 32 con PMCID) |
| 23c · Títulos en español | código hecho en la rama `fase-1-figuras-titulos` (v129–v132: `syn titles`, dbt, web, cola de Sofía, informe y pipeline), sin ninguna llamada real todavía. Falta la prueba real con ~40 títulos (OK aparte de Aday), que medirá cuántos fallan las comprobaciones y cuántos tokens cuestan; se fusiona después del 2026-11-17 |

**Qué cuenta como intervención** (Aday, 2026-11-13): una ejecución programada en rojo, o un commit de Aday que arregle el pipeline para que vuelva a correr. Agotar el cupo de Groq no cuenta, porque es lo normal cada día (D10). Los cambios de contenido o de diseño y las decisiones de Sofía tampoco: son trabajo, no rescates.

**Desde cuándo** (Aday, 2026-11-13): desde la primera ejecución programada con Groq, la del 2026-11-14, así que el cierre más temprano es el 2026-11-27. Sustituye a la regla del plan («cuando estén todas las casillas»). Los 14 días miden si el pipeline corre solo, y las casillas que faltan son trabajo de Sofía, no del pipeline. La fase sigue exigiendo los 14 días **y** todas las casillas **y** el visto bueno de Sofía. Un cambio que entre mientras corre el reloj y rompa una ejecución la pone en rojo y devuelve el contador a 0.

## Para qué servía esta fase

Montar la web que se actualiza sola cada día con lo mínimo que la hace útil y honesta:
- noticias de neurociencia de fuentes reales, con sus señales (revista o preprint, humanos o animales, retractado o corregido);
- resúmenes propios en inglés y español que pasan comprobaciones mecánicas y un juez de otra familia, o el texto de respaldo si no las pasan;
- las páginas fijas (Cómo evaluamos, Estado de los datos, Fuentes y licencias, Acerca de);
- y una ejecución diaria en GitHub Actions que no necesite a nadie.

Se hizo en **rebanadas verticales**: primero PubMed de punta a punta (ingesta → almacén → web mínima → pipeline), después el resto de fuentes, después la parte con LLM y al final la operación. Así, los fallos de cron, red y caché salían pronto, con poco código encima.

## Lo que se construyó

| Bloque | Pasos | Qué hace |
|---|---|---|
| Cimientos | 1–2 | `http.py` (reintentos, `retry-after`, User-Agent con contacto), `store.py` (solo escribe si cambia) e informe de cada ejecución en `runs/` |
| Ingesta | 3–9 | PubMed, Crossref (avisos de retractación y corrección), Europe PMC, bioRxiv y medRxiv, los RSS de Nature · Science · Cell, SINC, The Conversation, ScienceDaily y OpenAlex; `syn check` para saber si hay algo nuevo |
| Almacén | 10–11 | dbt sobre DuckDB reconstruido cada día: staging por fuente, un estudio por DOI (preprint ↔ publicado) y los marts `dim_study` y `fct_news_item` |
| Noticias | 12–15 | señales de cada estudio, filtro «¿es neurociencia?», clasificación por tipo (LLM y baseline TF-IDF) y agrupación de la misma noticia entre medios e idiomas |
| Textos | 16–20 | hechos → resumen EN → ES con comprobaciones (copia de 8 palabras, cifras, alarma, cautela, ortografía), juez `gpt-oss-120b`, `syn recheck`, carga inicial con Qwen 9B en local |
| Web | 21–27, R | Jinja2 sin framework, ES y EN, maqueta «Noche»; Neuro News, resumen semanal, Clásicos (solo lo aprobado), dato del día, «Explora por temas», cola y página de revisión de Sofía; `syn site --check` |
| Operación | 28–29 | `pipeline.yml` diario con respaldo y espejo semanal en BigQuery ([D10](../adr/0010-pipeline-diario.md)) |

## Lo que se decidió y por qué

### D2 · Copiar y adaptar el motor de Paleo ([ADR](../adr/0002-motor-comun.md))
Cada módulo copiado dice su origen en el docstring; no hay un paquete compartido. Paleo está en producción y no puede depender de lo que cambie aquí.

### Filtro de neurociencia (paso 13, v69): OpenAlex sí, MeSH no
El plan decía «reglas con MeSH u OpenAlex». Al medirlo, MeSH no servía: guardamos los identificadores sin su árbol, y la alternativa («el DOI entró por la consulta de neuro de PubMed») falló en 4 de 6 casos (metamateriales, adipocitos…), porque la consulta es amplia a propósito. Queda OpenAlex por DOI, y el LLM solo para lo que OpenAlex no conoce. En un día real, OpenAlex decide la mitad (169 de 336).

### Cupo diario de resúmenes (SCOPE §8, v98 y v103)
El cupo gratuito de Groq no da para resumir todo. La lista va por niveles (primero la neurociencia de Nature · Science · Cell) y, dentro de cada uno, lo más nuevo primero. Una fecha de número impreso no adelanta a nadie.

### La señal se llama «Publicado en revista», no «revisado por pares» (v98)
Que un artículo salga en una revista no prueba que tuviera revisión por pares, y «Cómo evaluamos» lo explica.

### Carga inicial: el cuello de botella es el juez (paso 20, v108, opción B)
Qwen 9B en local redactaría los 2032 candidatos en unas 5,6 h, pero el juez en Groq solo juzga unos 100 al día (200 000 tokens al día y unos 1900 por juicio). La carga se limitó a lo que el juez aprueba en dos días: 200 estudios.

### Pipeline diario ([D10](../adr/0010-pipeline-diario.md))
Caché privada en Actions, parada con el 429 de cupo diario, comprobación previa de la clave en rojo (opción A) y espejo de D1 los lunes. La idea central: **una ejecución en rojo significa algo que hay que mirar**. Eso es lo que hace medible «sin intervención».

### Web
- Diseño «Noche», elegido por Aday y Sofía tras tres rondas de maquetas (v76–v79).
- Fechas de número impreso (v102, opción A): si PubMed da una fecha futura, la tarjeta muestra el día en que entró en nuestros datos y aparte «número de enero de 2027».
- Huecos discretos (v113): una nota gris «pendiente», con la explicación al pasar el ratón.
- Dato del día (v115): una frase de un resumen ya verificado y aprobado por el juez, con su fuente; si no hay ninguno, no sale.
- «Explora por temas» (v118, opción B): cinco temas MeSH con al menos 3 piezas recientes y un interruptor de Sofía por tema. Emoción queda fuera hasta que ella lo confirme.

## Cifras

| Medida | Valor | Fuente |
|---|---|---|
| Clasificación, primera ejecución real (Qwen 9B, local) | 2707 piezas en 573 s; estudios: enfermedad 883, cerebro sano 564, ruido 539, técnica 482, ensayo clínico 103 | v106 |
| Prompts v2 (paso 18, 10 artículos) | 20 de 20 pasan comprobaciones y juez (17 de 20 con v1) | v107, [D4](../adr/0004-llm.md) |
| Carga inicial (200 estudios, Qwen 9B) | 34 min; inglés 184 pasan; español 123 → 165 tras `syn recheck` | v110 |
| Juez, día 1 | 83 juzgados, 67 aprobados (81 %), 16 rechazados; 101 pendientes | v111 |
| Espejo de BigQuery | unos 0,9 MB en Parquet (4053 estudios y 366 noticias) | v117 |
| Macro F1 del clasificador frente al baseline | *pendiente (14b)* | — |
| Precisión y recall de la agrupación | *pendiente (15)* | — |
| Primera ejecución con Groq: clasificados, resúmenes, juzgados y cupo | *pendiente (2026-11-14)* | — |
| Días autónomos | *pendiente* | `runs/` en la rama `data` |

## Conceptos, desde cero
- **Rebanada vertical:** construir una sola fuente de punta a punta (de la API a la página publicada) antes de ampliar. Los problemas de integración salen el primer día, no el último.
- **Texto de respaldo:** el texto que se construye solo con datos («Estudio en ratones publicado en *Neuron* el…») cuando el resumen del LLM no pasa las comprobaciones. La web nunca muestra un texto generado sin verificar.
- **Comprobaciones mecánicas frente a juez:** las primeras son código (cifras que coinciden, ninguna secuencia de 8 palabras copiada, palabras de alarma, ortografía). El juez es otro modelo que lee el abstract y el resumen. Cazan errores distintos: el día 1, el juez rechazó 16 textos por errores reales (datos que el abstract no dice, causalidad exagerada, ratas por ratones) que las comprobaciones no ven.
- **Idempotencia:** cada `syn …` deja el mismo resultado si se ejecuta dos veces. Por eso una ejecución que se corta a medias se arregla con la siguiente, sin limpiar nada a mano.
- **El estado en git:** los datos crudos, los textos y los registros van a la rama `data`. El almacén se reconstruye cada día desde ahí, así que no hay base de datos que respaldar.
- **Cupo diario como diseño:** el cupo gratuito no es un error que se reintenta, sino un presupuesto. El pipeline gasta lo que hay por orden de prioridad y deja el resto para mañana.

## Cómo se comprueba
- `uv run pytest` y `uv run ruff check . && uv run ruff format --check .` en la CI, sin red (fixtures, `httpx.MockTransport`, `FakeLLM`).
- `syn build` (dbt con tests de claves, relaciones, valores aceptados y frescura) sobre las fixtures en la CI, y sobre los datos reales en cada ejecución.
- `syn site --check`: hreflang, créditos, enlaces, páginas huérfanas, aviso médico en cada página y señales en cada estudio.
- Cada ejecución deja su informe en `runs/` de la rama `data`, y la página «Estado de los datos» lo muestra.
- Revisión visual en Chrome: ES y EN, claro y oscuro, 384 px y escritorio, contraste AA.
- La web publicada: https://adaycuestacorrea.github.io/synaptica/

## Qué salió mal (y qué se aprendió)
- **La caché de Actions empieza vacía** (v115–v116). En la primera ejecución en la nube no estaban los abstracts de lo ya ingerido, porque la caché no va en git. Ahora PubMed y bioRxiv vuelven a pedirlos para la ventana de 7 días. *Lección:* probar el arranque en frío, no solo el caso normal.
- **`syn judge` no lee `.env`** (v111). En local, la clave tiene que estar exportada. Eso motivó la comprobación previa de la clave en la CI.
- **Las comprobaciones en español daban falsos positivos** (v110): 61 de 184 textos fallaban, casi siempre por palabras que faltaban en el diccionario o por cautelas mal detectadas («more likely» compara probabilidades; no es prudencia). Tras corregirlas y añadir `syn recheck`, pasan 165; los 19 restantes son fallos legítimos. *Lección:* una comprobación también hay que medirla con datos reales.
- **`spanish_natural` del juez no discrimina**: pone 4 a casi todo (v107, v111). Por eso los textos v2 están en la cola de Sofía para que valore el español.
- **El clasificador dejaba sin tipo los artículos de Nature · Science · Cell** (v106): dos fallos de unión en dbt, corregidos con un test SQL.
- **MeSH no servía como regla** para el filtro de neurociencia (v69).
- **Fechas futuras de PubMed** (v102): 85 de 2571 candidatos tenían una fecha de número impreso posterior a hoy.
- *Pendiente: lo que salga de las ejecuciones con Groq y de los 14 días.*

## Cómo defenderlo en una entrevista
- «La web la escribe un LLM, pero nada se publica sin pasar comprobaciones mecánicas y un juez de otra familia. Si falla, sale un texto construido solo con datos. Medí las dos barreras por separado: cazan errores distintos.»
- «El cupo gratuito es un presupuesto, no un error. El pipeline gasta por prioridad y para en cuanto el proveedor dice que se acabó el día, en lugar de reintentar durante horas.»
- «Una ejecución en rojo significa que hay algo que mirar. Por eso la clave se comprueba antes, sin gastar tokens, y el cupo agotado no la pone en rojo. Así puedo medir “14 días sin intervención”.»
- «Los abstracts no se publican: viven en una caché privada de Actions, y la CI se recupera sola si GitHub la borra.»
- «Construí en rebanadas verticales: una fuente de punta a punta antes de añadir más. El fallo de la caché vacía salió el primer día en la nube, no en la última semana.»

## Lo que pasa a la Fase 2
*Pendiente al cierre.* Por ahora:
- 23b (figuras de PMC) y 23c (títulos en español), si no entran antes del cierre;
- el estudio de UX de Neuro Atlas y el visor en `site/static/` (ADR D3, v98).
