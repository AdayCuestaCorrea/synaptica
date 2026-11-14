# D10 — Pipeline diario: caché privada, cupo de Groq, clave comprobada y espejo

- **Estado:** aceptada (2026-11-13, Fase 1, pasos 28 y 29)
- **Relacionadas:** [D1](0001-almacen.md) (almacén y espejo) · [D4](0004-llm.md) (modelos y cupo) · [D5](0005-revision.md) (cola de Sofía) · [SCOPE §8](../../SCOPE.md#8-decisiones) · [`pipeline.yml`](../../.github/workflows/pipeline.yml)

## Resumen

| Pieza | Decisión | Por qué |
|---|---|---|
| Caché privada | `data/cache/` se guarda entre ejecuciones en la caché de Actions, nunca en git | Los abstracts no se pueden publicar, pero hacen falta para juzgar al día siguiente |
| 429 de cupo diario | Un 429 que dice «per day» (TPD o RPD) para el comando al momento; el resto queda con el texto de respaldo | Esperar no sirve cuando el proveedor cuenta por días |
| Clave de Groq | `syn doctor --llm groq` (`GET /models`, sin gastar tokens) antes del LLM, **sin** `continue-on-error` | Una clave que falta o que Groq rechaza pone la ejecución en rojo, en vez de dejarla en verde con textos de respaldo |
| Espejo de BigQuery | Paso del pipeline los lunes o a mano, con `continue-on-error` | Lo decide D1; aquí solo cómo encaja: la web nunca depende de él |

## Contexto

La Fase 1 se cierra tras 14 días seguidos de ejecución autónoma (SCOPE §7). El pipeline se adapta del de Paleo Atlas (D2): el estado vive en la rama `data`, el almacén DuckDB se reconstruye en cada ejecución (D1) y cada paso es un comando `syn`. Hay tres diferencias con Paleo que obligan a decidir:

1. **Hay datos que no se pueden publicar.** Los abstracts solo sirven para escribir y juzgar los resúmenes, y la regla es que no se publican. La rama `data` es pública, así que no pueden ir en ella. Pero el juez trabaja al día siguiente sobre estudios que entraron antes: los 101 de la carga inicial (paso 20) que se quedaron sin juzgar al agotarse el cupo del día 1.
2. **El cupo gratuito de Groq se agota cada día.** Son 1000 peticiones y 200 000 tokens al día por modelo (`GROQ_FREE`, `src/synaptica/llm.py:91`, del 2026-11-10). El 13 de noviembre el juez se paró tras 83 estudios (v111). El redactor reparte su cupo entre clasificar y resumir.
3. **Un fallo de la clave pasaba desapercibido.** Los pasos del LLM llevan `continue-on-error` para que la web se publique siempre. En Paleo, una clave caducada dejó la ejecución en verde con todo en texto de respaldo, y nadie lo vio. Aquí ya pasó en local: `syn judge` no lee `.env` (v111).

Restricciones: 0 €, repositorio público, ninguna dependencia nueva, la web publicada aunque falle una parte y los tests sin red.

## Decisión

### 1. Caché privada en la caché de Actions

- `data/cache/` (abstracts, citas privadas, caché del LLM y uso del cupo) se restaura al empezar (`actions/cache/restore`, clave `synaptica-cache-<run_id>` con el prefijo como `restore-keys`) y se guarda al final con `if: always()`, aunque haya fallado algo antes.
- La caché de Actions no se puede descargar desde la web ni con la API pública: solo la leen los workflows de este repositorio. **No es un secreto**: un workflow que se ejecute en una PR puede restaurar las cachés de la rama principal, también desde un fork. Para lo que guarda basta: los abstracts son públicos en PubMed, y la regla es no *publicarlos* en la web. En la caché nunca va una clave.
- El commit a la rama `data` **se niega** si hay algo de `cache/` o algún `.duckdb` preparado para commit. Es una segunda barrera, por si cambia el `.gitignore`.
- **Se recupera sola** (v116): Actions borra una caché que lleva 7 días sin usarse. Si pasa, `syn ingest pubmed` vuelve a pedir el registro MEDLINE de los estudios de los últimos 7 días que tienen abstract y no están en la caché, y `syn ingest biorxiv` guarda el abstract de todo lo que lista. La ventana de los resúmenes también es de 7 días, así que no se pierde nada que todavía se pudiera resumir.

### 2. 429 por cupo diario: parar, no reintentar

- `post_json` (`src/synaptica/llm.py`) reintenta los 429 y 5xx con espera exponencial y respeta `retry-after` (hasta 120 s), como en Paleo.
- Si el texto del 429 dice «per day», «(TPD)» o «(RPD)», lanza `QuotaExhausted` sin reintentar. Es la misma excepción que usa nuestro limitador cuando su propio contador llega al cupo del día (`RateLimiter`, que también espera al cupo por minuto).
- Cada comando atrapa `QuotaExhausted`, guarda lo hecho y termina. Lo pendiente se queda con el texto de respaldo y entra al día siguiente, en el orden del cupo (SCOPE §8, v98). Los comandos son idempotentes: lo que está al día se salta.
- El paso del LLM tiene un tope de 60 minutos, así que la web, la cola de Sofía, el informe y el commit se ejecutan siempre.

### 3. Comprobación previa de la clave (opción A de Aday)

- `syn doctor --llm groq` llama a `GET /models` de Groq. Esa llamada no gasta tokens ni cuenta para el cupo de los modelos. Devuelve exit 1 si la clave falta o si Groq la rechaza, y nunca la imprime (`check_key`, `src/synaptica/llm.py`).
- El paso va **sin** `continue-on-error`. Si falla, la ejecución sale en rojo y GitHub avisa a Aday, pero la web y el commit se ejecutan igual (`!cancelled()`), con los textos del día anterior o los de respaldo.
- Solo se ejecuta cuando hay LLM: en las ejecuciones programadas o a mano con `llm`.

### 4. Espejo de BigQuery dentro del pipeline

La decisión es la de D1 (DuckDB como almacén y BigQuery como espejo semanal de los marts). Así se lleva a cabo:

- Los lunes (UTC) o a mano con `mirror`. Autenticación por Workload Identity Federation (S2), sin ninguna clave guardada.
- `syn mirror export` saca solo los marts (`dim_study`, `fct_news_item`) a Parquet con el `COPY` de DuckDB y se niega por encima de 1 GiB. Después, `bq load --replace` por tabla: las cargas son gratis y no necesitan DML.
- `syn mirror record` anota filas, bytes en Parquet y bytes almacenados (`bq show`) en `mirror/bigquery.jsonl` de la rama `data`, porque los 10 GiB del sandbox son para siempre.
- Va con `continue-on-error`: si el sandbox cambia o se agota, la web no se entera.
- La autenticación (WIF) también va con `continue-on-error`, y el espejo solo corre si salió bien (v139). Antes no lo llevaba: un fallo de la federación habría puesto en rojo la ejecución del lunes y contado como intervención en el reloj de cierre. ~~El informe de la ejecución sigue marcando el paso como fallido.~~ **Era falso** (corregido en la v143, ver «Revisión»): la API marca como «success» un paso con `continue-on-error` aunque falle, y ahora el pipeline le pasa al informe el resultado real.

## Alternativas consideradas

### Caché privada
- **A · Caché en git, en un repositorio privado aparte.** Sería duradera, pero hace falta un token con acceso a otro repositorio (un secreto más) y abstracts guardados para siempre en un historial de git. Descartada.
- **B · Sin caché: volver a descargar cada día.** Es simple, pero son muchas más peticiones a PubMed y bioRxiv, va en contra de la regla «cachea» y el juez dependería de que la fuente responda ese día. Queda solo como mecanismo de recuperación (v116).
- **C · Caché de Actions (elegida).** Es gratis, privada del repositorio y no necesita ningún secreto. Su punto débil, que se borra a los 7 días sin uso, se cubre con la recuperación de la v116.

### 429 de cupo diario
- **A · Reintentar con espera, como cualquier 429.** Con cientos de estudios pendientes, el paso se pasaría horas esperando hasta el tope sin conseguir nada. Descartada.
- **B · Fiarse solo del contador propio.** Groq cuenta también lo que se gastó fuera de esta ejecución (por ejemplo, una prueba en local el mismo día), así que nuestro contador puede ir por detrás. Hace falta las dos cosas.
- **C · Distinguir el 429 diario por su texto (elegida).** Depende del texto del mensaje de Groq, pero si Groq lo cambia, el resultado es reintentar y esperar más, no un fallo silencioso.

### Clave de Groq
- **A · Comprobación previa sin gastar tokens, en rojo si falla (elegida por Aday, paso 28).**
- **B · Contar los textos de respaldo en el informe y avisar si superan un umbral.** Llega tarde, mezcla «sin clave» con «sin cupo» y obliga a elegir un umbral.
- **C · Quitar `continue-on-error` del paso del LLM.** Pondría en rojo cualquier agotamiento del cupo, que es normal todos los días.

### Espejo
- Las alternativas (BigQuery como almacén, solo vistas…) están en D1. Aquí solo se descartó ponerlo en un workflow aparte: tendría que reconstruir el almacén otra vez o descargar los marts de algún sitio, y el pipeline ya los tiene.

## Consecuencias

- Una ejecución en rojo significa **algo que Aday tiene que mirar**: una fuente que falla, la clave, dbt o la web. Agotar el cupo no la pone en rojo. Esto es lo que hace medible el criterio de cierre de la Fase 1 («sin intervención»).
- Los abstracts solo existen en la caché de Actions y en la caché local de Aday (`~/synaptica-data`). Si se pierden las dos, la recuperación los vuelve a pedir para los últimos 7 días. Lo anterior se queda como esté.
- El atraso de textos se recupera solo, a ritmo de cupo. Si crece, Ollama lo recupera en local (D4).
- `review-intake.yml` también lee los abstracts de la caché de Actions para comprobar las correcciones de Sofía (D5).
- Si Groq cambia sus límites o el texto de sus 429, hay que actualizar `GROQ_FREE` y `_daily_limit`. [`spikes/s5/groq_limits.py`](../../spikes/s5/groq_limits.py) compara los límites con las cabeceras de respuesta.

## Pruebas

- Tests sin red: reintento de 429 y 5xx con `retry-after` (`tests/test_http.py`); parada inmediata del 429 diario y reintento de los demás, y `check_key` sin clave, con 401 y con 200 y `syn doctor --llm groq` (`tests/test_cli.py`); `syn mirror export` y `record` (`tests/test_mirror.py`); el tope diario del contador propio: para antes de llamar, por tokens y por peticiones; lo lee una ejecución nueva el mismo día; va por modelo, y vuelve a empezar el día siguiente en UTC (`tests/test_llm_quota.py`).
- Tres ejecuciones manuales sin LLM en verde el 2026-11-13: [43445443061](https://github.com/AdayCuestaCorrea/synaptica/actions/runs/43445443061) (la primera, con la caché de Actions vacía, que destapó lo arreglado en la v116), [43451355876](https://github.com/AdayCuestaCorrea/synaptica/actions/runs/43451355876) y [43453985082](https://github.com/AdayCuestaCorrea/synaptica/actions/runs/43453985082).
- Juez en local el día 1 (v111): se paró solo al agotar el cupo, tras 83 estudios.
- Primer espejo real: ejecución manual [43512077811](https://github.com/AdayCuestaCorrea/synaptica/actions/runs/43512077811) del 2026-11-13, en verde. Crea el dataset `synaptica` (EU) y carga `dim_study` (4313 filas, 1,7 MB almacenados) y `fct_news_item` (373). El log trae avisos `gcloud.config.config-helper … no active account`, inofensivos: `bq` usa las credenciales de la federación.

## Revisión (2026-11-14): primera ejecución programada con Groq

[Run 43600053060](https://github.com/AdayCuestaCorrea/synaptica/actions/runs/43600053060). La lanzó el cron de las 06:17, pero arrancó a las 13:30 UTC (7 h 13 min tarde; Paleo tiene retrasos parecidos cada día). En verde, con «Status: ok» en el informe.

| | Cifra |
|---|---|
| Ingesta | PubMed 679 nuevos; Crossref 118 avisos; Retraction Watch 63 registros; Europe PMC 76; preprints 25; noticias 1 |
| dbt | 97/97 las dos veces |
| Elementos clasificados | **0** |
| Resúmenes escritos / verificados / juzgados | **0 / 0 / 0**; los 101 juicios pendientes de la carga inicial (v111), sin hacer |
| Cupo de Groq | 5 peticiones rechazadas, sin tokens |

**Qué falló.** `syn news neuro` recibió un 429 que no era de cupo: *Request too large for model `qwen/qwen3.8-27b` … output tokens per minute (OTPM): Limit 1000, Requested 1500*. Groq ha puesto a la organización un tope de 1000 tokens de salida por minuto para Qwen, aparte del de tokens por minuto (el 2026-11-13 una llamada con `max_tokens=4000` pasó). Groq cuenta el `max_tokens` como salida prevista *antes* de ejecutar: una petición que pide más que el tope se rechaza sin ejecutarse.

Además, el diseño lo agravó en dos cosas:
1. El paso era un script con `bash -e`: el primer error dejó sin correr `classify`, `group`, `facts`, `write`, `recheck` y `judge`.
2. **El fallo no se vio.** La API de GitHub da `conclusion: success` a un paso con `continue-on-error` que falla, y `syn report` se fiaba de ella. Por eso el informe dijo «ok» y el respaldo no lo reintentó. Lo mismo valía para la autenticación de Google: lo que dice la v139 sobre ella era falso.

**Arreglo (v143, opción A + C de Aday).**
- **A, ajustarse al tope.** `Limits.output_tokens_per_minute` y `MODEL_LIMITS`: Qwen en Groq con 1000. El limitador reserva el `max_tokens` de cada llamada en la ventana de un minuto, y `complete_json` lo recorta al tope (también al reintentar con más tokens). Un 429 «Request too large» no se reintenta. Los `max_tokens` se fijan por llamada a partir de las salidas medidas en la caché local (999 respuestas: frases EN máx. 342 y ES 381; hechos con Qwen en Groq máx. 874; lotes de 20 elementos máx. 496; juez máx. 342): neuro y group 600, classify 800, facts 1000, frases EN y ES 800 (resumen semanal 1000), juez 800 como estaba.
- **C, que no vuelva a pasar en silencio.** Cada comando del LLM corre aunque falle el anterior, y el paso falla al final si alguno falló. El pipeline pasa a `syn report finish` el `steps.<id>.outcome` real del paso del LLM, de la autenticación y del espejo (`--outcome`). Si alguno falló, la ejecución queda «failed» y la de respaldo lo reintenta.
- **Ritmo.** Con el tope salen unos 2,6 minutos por estudio (hechos + EN + ES), así que `facts` y `write` bajan a `--limit 20` y cada comando tiene su plazo con `--until`. El juez corre primero, con lo pendiente de días anteriores, y otra vez al final. El paso sube a 75 minutos.

**Consecuencia.** Menos resúmenes al día (unos 20 en vez de 40) mientras dure el tope. Si Groq lo quita o resulta ser solo de Qwen, `MODEL_LIMITS` es el único sitio que hay que cambiar. Aday mirará el desglose «in / out» de cada modelo en la página de límites de su cuenta de Groq.

**Reloj de cierre.** Aday decide reiniciarlo (v144): el arreglo es un commit que hace funcionar el pipeline, y se acumulaban fallos de Actions.

## Revisión (2026-11-14, tarde): la ejecución manual con el arreglo, cortada

[Run 43609191046](https://github.com/AdayCuestaCorrea/synaptica/actions/runs/43609191046), a mano con Groq y el arreglo de la v143. El tope de salida ya no tumbó ninguna llamada: el filtro respondió 206 elementos en 10 minutos y la clasificación, 641 en 33 minutos (una llamada por minuto). A los 45 minutos de paso, el job se cortó con *The operation was canceled*. Aday no lo canceló, no saltó ningún tiempo límite y GitHub no tenía incidencias publicadas. **No corrió ni un paso con `always()`, ni siquiera los «Post»**: fue un corte duro, no una cancelación normal. Se perdieron las 847 decisiones (estaban en `derived/`, sin commit) y buena parte del cupo de Qwen del día.

**Lección.** Un pipeline que solo guarda al final lo pierde todo con un corte duro, y `always()` no protege de eso. Como la causa no está en nuestras manos, el diseño tiene que asumir que puede repetirse.

**Arreglo (v145).**
- **Tres etapas de Groq**, cada una con su plazo y `continue-on-error`: juez de lo pendiente (gpt-oss, con cupo propio, así que no espera a nadie) → filtro y clasificación → hechos, resúmenes y juez de lo nuevo.
- **Un punto de guardado tras cada etapa** (`scripts/commit_data.sh checkpoint`): commit y push de lo producido a la rama `data`, sin `runs/` (el registro de la ejecución se completa al final). Es el mismo script del commit final, con su misma comprobación de archivos privados. Tras la última etapa, un guardado intermedio de la caché, porque las citas de los hechos solo viven allí.
- **La clasificación en lotes de 40** (antes 20) con `max_tokens` 1000: una respuesta ocupa unos 25 tokens por elemento, y así salen la mitad de llamadas bajo el tope. Lleva `--limit 800`, que cubre los ~650 elementos nuevos de cada día. El lote de 20 fue el que se midió en S5; si Sofía ve peor la clasificación con el 14b, se vuelve a 20.
- El job pasa a 150 minutos: las tres etapas suman como máximo 115.

## Revisión (2026-11-14, noche): primera ejecución con las etapas

[Run 43614465935](https://github.com/AdayCuestaCorrea/synaptica/actions/runs/43614465935), a mano con Groq. Terminó entera y el informe dice **«failed»** por un paso tolerado que falló: la parte C de la v143 funciona.

| Etapa | Resultado |
|---|---|
| Juez de lo pendiente | 71 juzgados en 20 min (60 aprobados, 11 rechazados; 2 sin abstract en caché) |
| Filtro y clasificación | 172 elementos respondidos por el LLM; 513 clasificados en 17 min, con **128 sin respuesta** (lotes de 40); después, `syn news group` 15 min sin salida, hasta el tiempo límite de 40 min de la etapa |
| Hechos y resúmenes | 0: el cupo diario de Qwen (200 000 tokens) estaba agotado por la ejecución cortada |
| Juez de lo nuevo | 30 juzgados (28 aprobados, 2 rechazados) |

Con eso **quedan juzgados los 101 de la carga inicial**: no queda ningún estudio pendiente del juez (212 con textos en la rama `data`).

**Fallos y arreglo (v146).**
- **Los puntos de guardado no subieron nada.** Hicieron su commit, pero el `git pull --rebase` se negó porque `runs/` (versionado y modificado, fuera del commit a propósito) quedaba sin guardar. Esos commits subieron con el final; en un corte duro se habrían perdido. Ahora el pull lleva `--autostash`, probado reproduciendo el caso (`runs/` modificado y el remoto un commit por delante).
- **Lotes de 40: el modelo deja sin responder uno de cada cinco.** Se vuelve a lotes de 20 (0 sin respuesta en la ejecución anterior).
- **Un comando podía comerse la etapa.** Cada comando del filtro y la clasificación lleva su tiempo máximo (`timeout`): filtro 8 min, clasificación 20, agrupación 5, dbt 4. El filtro y la clasificación guardan cada lote, así que un corte pierde un lote como mucho; la agrupación guarda al final y, si no le da tiempo, lo intenta al día siguiente. La clasificación ya no lleva `--limit`: hace lo que quepa en sus 20 minutos.

