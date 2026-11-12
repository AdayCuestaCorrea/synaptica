# Plan de la Fase 1 — La base

## Contexto

La Fase 0 está a punto de cerrarse: faltan D3, que se acepta tras la opinión de Sofía esta tarde, y D5, que depende de la prueba de S4. Aday quiere tener preparado el plan de la Fase 1 (SCOPE §7, 13 casillas): pasos pequeños, cada uno con su commit, sus tests sin red y su criterio de hecho, siguiendo los patrones de `../paleo-atlas`. Los pasos que dependen de D5 quedan marcados y aparcados. **No se programa nada hasta que se cierre la Fase 0.**

Aprobado por Aday el 2026-11-12 (SCOPE v53). Las rutas de Paleo Atlas son relativas a `../paleo-atlas/`.

## Reglas comunes a todos los pasos

- **Un commit por paso**, con su casilla o subcasilla y una línea en §11. Tests con el subagente `test-runner` (`uv run pytest`, `uv run ruff check . && uv run ruff format --check .`).
- **Sin red:** `httpx.MockTransport` (patrón de `paleo/http.py:32`), `FakeLLM` (patrón de `paleo/tests/test_news.py:13`) y `SYN_DATA_DIR` en `tmp_path`. Se reutilizan las fixtures de S1 que ya están en `tests/fixtures/`.
- **Código copiado:** cada módulo indica su origen en el docstring (por ejemplo `paleo-atlas/src/paleo/store.py`). Es la opción «copiar y adaptar» de D2, elegida por Aday; se cierra con un ADR en el paso 1.
- **Licencias:** abstracts y texto completo solo en `data/cache/` (no versionado, como en `paleo/narrative/sources.py:253`). En la rama `data`, solo metadatos con su licencia.

## Pasos

Leyenda: 🟢 se puede hacer en cuanto cierre la Fase 0 · 🟡 depende de D5 (después del ADR 0005) · 🔵 depende de algo externo (la GPU de Aday, secretos o ajustes de GitHub, que confirma él).

### A. Cimientos del paquete
| # | Paso | Origen en Paleo / S | Tests sin red | Hecho cuando |
|---|---|---|---|---|
| 1 ✅ | `http.py` (reintentos 429/5xx, Retry-After, User-Agent con contacto de `config.py`) y `store.py` (`raw/<fuente>/<tipo>/<clave>/<fecha>.json`, solo escribe si cambia, `_checked.json`, fechas en UTC); ADR de D2. pydantic entra como dependencia cuando la use un módulo (16 o la cola de revisión) | `paleo/http.py`, `paleo/store.py` | reintentos y backoff con reloj falso; escribir dos veces lo mismo = 0 cambios | pytest verde; `docs/fuentes.md` aclara el User-Agent genérico de `spikes/s1/common.py` |
| 2 ✅ | `report.py` y `syn report start/finish/ran-today` → `runs/<fecha>.json` | `paleo/report.py` | informe en tmp, idempotente | cada paso posterior puede anotar sus cifras |

### B. Ingesta (un commit por familia de fuentes)
| # | Paso | Tests | Hecho cuando |
|---|---|---|---|
| 3 ✅ | `syn ingest pubmed`: esearch y esummary en `raw/`; efetch (abstract) solo a la caché; `NCBI_API_KEY` opcional (3 o 10 req/s) | fixtures `pubmed/` | crudos deterministas y límite respetado (test con reloj) |
| 4 🟢 | `syn ingest europepmc`: metadatos y licencia OA; texto completo a la caché | `europepmc/` | idem |
| 5 🟢 | `syn ingest biorxiv` (bio y med): ventana hacia atrás y versiones deduplicadas por DOI | `biorxiv/`, `medrxiv/` | dos versiones → un estudio |
| 6 🟢 | `syn ingest journals`: 7 RSS + Crossref por ISSN de respaldo, solo metadatos | `journals/` | sin texto de editores (amplía `test_fixtures.py`) |
| 7 🟢 | `syn ingest news`: SINC, The Conversation EN/ES y ScienceDaily desde la semilla `news_feeds.csv`, con licencia por feed | `news/` | `has_new_items` probado |
| 8 🟢 | Crossref ✅ (`syn ingest crossref`: lista diaria de avisos de todas las disciplinas, no consulta DOI a DOI; falta cubrir las retractaciones que solo conoce Retraction Watch) y OpenAlex (citas, `filter`, nunca `search`) | `crossref/`, `openalex/` | cupos de §5 respetados |
| 9 🟢 | `syn check`: detección barata, que sale 0, 1 o 2, y un error de red nunca cuenta como «sin cambios» (lección de Paleo) | MockTransport con errores | ADR breve «detección de cambios» (copia del 0010 de Paleo) |

### C. Almacén (dbt + DuckDB, D1)
| # | Paso | Tests | Hecho cuando |
|---|---|---|---|
| 10 🟢 | Proyecto dbt sobre DuckDB, macro `raw_store` (`read_json` con glob), staging por fuente; `syn build`; `scripts/seed_fixture_data.py` para la CI | unique, not_null y accepted_values; frescura con `stg_raw__checked` + `assert_*_is_fresh.sql` y cadencia en una semilla | `syn build` verde en la CI con fixtures |
| 11 🟢 | Intermediate: estudio unificado por DOI, preprint ↔ publicado, versiones | relationships y test SQL «un DOI, un estudio» | marts `dim_study` y `fct_news_item` |

### D. Noticias
| # | Paso | Tests | Hecho cuando |
|---|---|---|---|
| 12 🟢 | **Señales**: revisado o preprint (fuente y tipo de Crossref), humanos o animales (MeSH Humans/Animals de PubMed; si no hay, «sin dato», nunca se inventa), retractado o corregido | accepted_values; test SQL «todo estudio mostrado tiene sus 3 señales (o "sin dato")» | señales en el mart |
| 13 🟢 | **Filtro «¿es neurociencia?»** para las revistas generalistas: reglas (MeSH u OpenAlex por DOI) y el LLM solo cuando no hay dato | casos de las fixtures `journals/` | medido sobre los RSS de S1 |
| 14a 🟢 | **Clasificación** por tipo con LLM (lotes de 20, caché por hash + versión del prompt) + baseline TF-IDF con regresión logística, y `syn eval news` | FakeLLM; métricas sobre un gold de prueba | comando listo, a falta de etiquetas reales |
| 14b 🟡 | ~100 titulares etiquetados por Sofía → macro F1 del LLM frente al baseline; con los mismos ~100 se valida el juez (ADR D4) | validación del gold | cifras en el informe y en `fase-1.md` |
| 15 🟢 | **Agrupación**: primero DOI exacto; después pares candidatos en una ventana de 5 días, decididos por el LLM y cacheados en `pairs.json`, con union-find; entre idiomas | pares de las fixtures; gold de pares etiquetado por Aday (no es contenido de salud) | precisión y recall de los pares en el informe |

### E. Textos LLM
| # | Paso | Tests | Hecho cuando |
|---|---|---|---|
| 16 🟢 | Pasar a `src/synaptica/narrative/` `llm.py`, `checks.py`, `pipeline.py` y los prompts v2 de S5; `syn facts`, `syn write`; texto de respaldo con datos (patrón de `paleo/site/fallback.py`) | FakeLLM; un texto que falla → respaldo; 8 palabras copiadas → falla | la cadena con fixtures publica o cae al respaldo |
| 17 🟢 | Comprobaciones nuevas: frases de alarma, se conserva la cautela de cada hecho y ortografía en español (la dependencia se justifica en el paso, con 2–3 opciones) | casos de la revisión de Sofía en S5 | cada comprobación con su test positivo y negativo |
| 18 🔵 | Repetir S5 con v2 en Groq (gasta cupo: lo autoriza Aday) y con Qwen 9B cuando la GPU esté libre; comparar con la revisión de Sofía | — (ejecución real) | tabla en el ADR D4 |
| 19 🟢 | Juez de otra familia (`gpt-oss-120b`) integrado en la cadena; `spanish_natural` no bloquea | FakeLLM del juez | veredicto del juez en el informe |
| 20 🔵 | Carga inicial con Qwen 9B en local, cuando terminen los lotes de Paleo | — | cifras de la carga en el informe |

### F. Web
| # | Paso | Tests | Hecho cuando |
|---|---|---|---|
| 21 🟢 | Esqueleto: `build.py` con Jinja2, `i18n/{es,en}.toml`, rutas `es/` y `en/`, plantilla base con el aviso médico y el pie de licencias; `syn site --check` copiado de Paleo (hreflang, créditos, enlaces, huérfanas) **más** aviso médico en cada página y señales en cada estudio | build con datos sembrados | `site --check` verde |
| 22 🟢 | Páginas fijas: Cómo evaluamos, Fuentes y licencias (generada desde la semilla de fuentes), Estado de los datos (desde `runs/`), Acerca de | `site --check` | las cuatro en ES y EN |
| 23 🟢 | Neuro News: Última hora y Nature · Science · Cell, con sus señales | idem | portada con datos de fixtures |
| 24a 🟢 | Clásicos: propuesta semanal por citas de OpenAlex, que entra en la cola de Sofía; mientras no esté aprobado, el bloque no muestra nada | test «nada sin aprobar» | propuesta generada |
| 24b 🟡 | Aprobación de los Clásicos por el flujo D5 | — | bloque con los aprobados |
| 25 🟢 | Resumen semanal (misma cadena y comprobaciones) | FakeLLM | página semanal ES y EN |
| 26 🟢 | Dato curioso del día (**hueco en SCOPE**: no dice de dónde sale; propuesta: un hecho ya verificado de los resúmenes del día, con su cita) | test «el dato tiene fuente» | se decide con Aday antes del paso |
| 27 🔵 | Pages: el sitio en la raíz, con la maqueta de S3 en `/spikes/s3/c/` (fusionar `pages.yml`; lo confirma Aday) | — | publicado y medido |

### G. Operación
| # | Paso | Tests | Hecho cuando |
|---|---|---|---|
| 28 🔵 | `pipeline.yml`: cron y respaldo, `syn check`, ingesta, LLM con `continue-on-error`, build, site + check, informe y commit en la rama `data` (rechaza `cache/` y `.duckdb`); secretos `NCBI_API_KEY` y `GROQ_API_KEY` con el OK de Aday | ejecución manual en seco | primera ejecución verde |
| 29 🔵 | Espejo semanal de los marts en BigQuery (load jobs, WIF ya creado; cupo de 10 GiB de por vida medido en el informe) | test de la selección de marts y del tamaño | consumo anotado |
| 30 | 14 días autónomos, visto bueno de Sofía y `fase-1.md` | — | cierre |

**Integración de la cola de revisión (🟡):** pasar `spikes/s4/` (models, intake, apply, review_page) a `src/synaptica/review/` según lo que diga el ADR 0005. Lo necesitan el 14b y el 24b. Nada más de la Fase 1 depende de D5, porque solo Neuro Diseases bloquea la publicación, y es de la Fase 3.

## Decisiones de Aday (2026-11-12)

1. **Orden: rebanada vertical.** Las tablas de arriba agrupan los pasos por tema; el orden de trabajo es este:
   - **Rebanada 1 (PubMed de punta a punta):** 1 (+ ADR de D2) → 2 → 3 → 8, solo la parte de Crossref (retractaciones) → 10 y 11, solo PubMed → 12 → 21 → 23, solo Última hora → 9 → 28 en ejecución manual. Al acabar: web mínima bilingüe con estudios reales y sus señales, y un pipeline que corre. Los errores de cron y de red salen en la primera semana.
   - **Rebanada 2 (más fuentes):** 4, 5, 6, 7, el resto del 8 (OpenAlex) y la ampliación de 10 y 11 a todas → 13 → 23, con Nature · Science · Cell.
   - **Rebanada 3 (inteligencia):** 14a → 15 → 16 → 17 → 19 → 25 → 26 (antes se decide de dónde sale el dato curioso) → 22 → 24a.
   - **Rebanada 4 (operación):** 27 → 28 con cron → 29 → 18 y 20 (🔵, cuando haya cupo o GPU).
   - **Tras D5:** pasar la cola de S4 a `src/synaptica/review/` → 14b → 24b.
   - **Cierre:** 30. El reloj de los 14 días arranca cuando estén todas las casillas.
   - **Excepción (v54–v56):** antes de cerrar la Fase 0 se adelanta, en la rama `fase-1`, todo lo que no necesita a Sofía ni toca GitHub: la rebanada 1 sin el paso 28.
2. **D2:** copiar y adaptar; se cierra con un ADR breve en el paso 1, el primer commit de la Fase 1, no antes.
3. **Etiquetas de Sofía:** por el flujo D5, como un tipo más de elemento de su cola (14b).
4. **Filtro de neurociencia:** primero reglas (MeSH de PubMed o temas de OpenAlex por DOI) y el LLM solo para los que quedan sin dato; se mide contra las etiquetas del 14b.

## Verificación del plan

- Cada casilla de SCOPE §7 Fase 1 tiene al menos un paso (comprobado: 13 de 13).
- Al ejecutarlo (más adelante): cada paso pasa `test-runner`, ruff, y `syn build` y `syn site --check` cuando aplican; las pruebas visuales, en Brave con Claude in Chrome.
