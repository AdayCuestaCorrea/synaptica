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
- **Pendiente de verificar:** la primera ejecución con Groq (la programada del 2026-11-14) y el primer espejo real (un lunes, o a mano con el OK de Aday). Sus cifras se añadirán aquí como «Revisión».
