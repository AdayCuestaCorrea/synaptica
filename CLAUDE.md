# SYNAPTICA — instrucciones para Claude Code

Web de neurociencia en español e inglés que se actualiza sola cada día: noticias científicas con resúmenes verificados y secciones para aprender cómo funciona el cerebro. La hacen Aday (desarrollo) y Sofía (doctorado en neurociencia, revisión del contenido). Reutiliza el «motor» de Paleo Atlas.

Documentos de referencia:

- `SCOPE.md`: **fuente de verdad** de qué se hace y en qué orden (fases, casillas, decisiones, registro de cambios). Léelo al empezar cada sesión.
- `docs/propuesta.md`: el producto tal como lo aprobó Sofía, en lenguaje no técnico. Léelo cuando la tarea toque contenido o diseño.
- `docs/adr/`: por qué se tomó cada decisión de arquitectura.

## Cómo trabajamos

- **Aday decide; tú propones y escribes el código.** Ante una decisión de diseño, da 2–3 opciones con pros, contras y tu recomendación, y espera su respuesta. No cierres por tu cuenta ninguna decisión de la lista «Abiertas» de `SCOPE.md`.
- Explica el porqué de lo que haces, no solo el qué: Aday tiene que entenderlo y poder defenderlo en una entrevista.
- Una fase cada vez. No adelantes trabajo de fases futuras salvo que se pida.
- Tareas pequeñas y verificables, con un commit por paso lógico.
- Al terminar una tarea, marca su casilla en `SCOPE.md` y añade una línea al registro de cambios. Si cambió una decisión, escribe o actualiza su ADR.
- Si algo de `SCOPE.md` parece equivocado o desfasado, dilo. No lo cambies en silencio.

## Personas

- **Aday**: dueño del repositorio, ingeniero de datos. Trabaja en CachyOS (Linux).
- **Sofía**: revisora del contenido científico. No es técnica, así que su flujo nunca puede exigir terminal, git ni editar YAML a mano. Dedica alrededor de 1 h al día a revisar.

## Reglas que no se rompen

**Coste.** 0 € al mes: planes gratuitos sin tarjeta, GitHub Actions, GitHub Pages y modelos locales. Si un servicio pide tarjeta o es una prueba limitada, no se usa.

**Contenido de salud.**
- El aviso «no es consejo médico» se ve en todas las páginas. La web nunca recomienda tratamientos.
- Una ficha de Neuro Diseases solo se genera si su aprobación por Sofía está registrada en los datos (por ejemplo `reviewed_by`, `reviewed_at`).
- Cada estudio muestra sus señales: publicado en revista o preprint (la web explica en «Cómo evaluamos» que lo primero no prueba la revisión por pares), en humanos o en animales, retractado o corregido.

**Textos generados con LLM.**
- Pasan las mismas comprobaciones que en Paleo Atlas: cada frase cita su fuente, las cifras y los nombres coinciden con ella, y nunca hay 8 o más palabras seguidas copiadas.
- Un texto que no pasa no se publica; en su lugar se muestra el texto de respaldo construido con datos.
- Las correcciones de Sofía pasan también las comprobaciones mecánicas (el juez solo avisa). Si una falla, vuelve a su cola con el aviso y ella la corrige o la mantiene con un motivo registrado (ADR D5).
- No se publican abstracts ni párrafos de los artículos, solo resúmenes propios con enlace al original.

**Licencias.**
- A diferencia de Paleo Atlas, se aceptan licencias NC (no comerciales).
- Cada fuente, imagen y modelo 3D registra su licencia y su autor, y la web los muestra.
- Los datos de atlas distintos (por ejemplo Waxholm, CC BY 4.0, y Julich-Brain, CC BY-NC-SA 4.0) nunca se combinan en un mismo dato derivado: el resultado heredaría la licencia más restrictiva. La RM de plantilla de Waxholm es otro conjunto de datos, CC BY-SA 4.0.
- De Nature, Science y Cell solo se usan metadatos y enlaces de sus canales públicos (RSS o APIs de metadatos). No se descargan las páginas de los artículos.

**Red y fuentes.**
- Respeta los límites de cada API, identifica las peticiones (User-Agent con un contacto) y cachea.
- Los tests y la CI nunca usan la red: trabajan con fixtures en `tests/fixtures/`.

**Secretos.** Nunca en el repositorio ni en los logs. En local van en `.env` (incluido en `.gitignore`); en la CI, en los secretos de GitHub Actions.

**Idiomas.** Español e inglés desde el principio. Ninguna página existe en un idioma sin su versión en el otro.

## Stack

- **Decidido:** Python 3.14 con uv · ruff · pytest · typer (CLI `syn`) · httpx · pydantic · dbt · Jinja2 + JavaScript sin framework · GitHub Actions (ejecución diaria) · GitHub Pages.
- **Almacén (D1):** DuckDB reconstruido cada día; espejo semanal de los marts en BigQuery sandbox (load jobs con Workload Identity Federation). Sin incrementales ni snapshots de dbt.
- **Pendiente** (ver `SCOPE.md`, decisiones abiertas): visor 3D, modelos LLM y flujo de revisión de Sofía.
- **No se usa:** Airflow ni Docker (ya demostrados en Paleo Atlas), Snowflake, ni frameworks de frontend salvo que un ADR lo justifique.

## Relación con Paleo Atlas

- El repositorio de referencia es `../paleo-atlas`, un clon local de github.com/AdayCuestaCorrea/paleo-atlas. Léelo antes de diseñar algo que allí ya existe. No lo modifiques desde aquí.
- Patrones que se reutilizan:
  - el estado vive en git (rama `data`) y el almacén se reconstruye en cada ejecución;
  - cada paso es un comando independiente del orquestador;
  - textos en cadena: hechos → texto EN → texto ES → comprobaciones;
  - clasificación y agrupación de noticias;
  - glosario;
  - `site --check`;
  - informe de cada ejecución.
- El código se copia y se adapta, no se importa entre repositorios. Cada módulo copiado indica su origen en el docstring. Los dos repositorios son del mismo autor.
- Los textos propios de Paleo (fichas, recaps, glosario) no se copian: se reescriben. Allí son CC BY-NC-SA y aquí serían CC BY-SA, así que copiarlos les quitaría la restricción NC. El código sí se copia, porque los dos son AGPL.

## Estructura (objetivo; se crea en la Fase 0)

```
src/synaptica/       cli.py, ingest/, parse/, news/, narrative/, glossary/, atlas/, site/
dbt/                 staging → intermediate → marts
site/                templates/, static/
tests/               fixtures/ (sin red)
docs/                propuesta.md, fuentes.md, adr/, fases/
.github/workflows/   ci.yml, pipeline.yml
```

## Comandos

```sh
uv sync
uv run syn --help
uv run syn doctor                         # entorno y variables necesarias (exit 1 si falta algo)
uv run syn doctor --llm groq              # … y que Groq acepta la clave (sin gastar tokens): la CI se pone en rojo si no
uv run syn report start --trigger local   # abre el registro de una ejecución en data/runs/
uv run syn report finish                  # lo completa e imprime el informe en Markdown
uv run syn report ran-today               # exit 0 si hoy (UTC) ya hubo una ejecución correcta
uv run syn check                          # ¿algo nuevo? exit 0 sí, 1 no, 2 la comprobación falló
uv run syn ingest pubmed --days 3         # registros nuevos de PubMed a data/raw/pubmed/ (abstracts solo a data/cache/)
uv run syn ingest crossref --days 3       # avisos de retractación, corrección… a data/raw/crossref/notices/
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run syn ingest europepmc --days 3      # acceso abierto de Europe PMC (el texto completo, bajo demanda)
uv run syn ingest biorxiv --days 7        # preprints de bioRxiv y medRxiv + enlaces a su versión publicada
uv run syn ingest journals                # RSS de Nature, Science y Cell (Crossref por ISSN de respaldo)
uv run syn ingest news                    # SINC, The Conversation y ScienceDaily
uv run syn ingest openalex                # tema y citas por DOI de las revistas generalistas
uv run syn ingest classics                # los más citados de cada subcampo, una vez por semana (Clásicos)
uv run syn news neuro [--provider groq]   # ¿es neurociencia? reglas de OpenAlex; el LLM solo con --provider
uv run syn news classify --provider groq  # tipo de cada pieza de Neuro News (lee el almacén: antes syn build)
uv run syn news group --provider groq     # misma noticia entre medios e idiomas (pares al LLM)
uv run syn titles --provider groq [--limit N]   # títulos en español de lo que enseña la web, con comprobaciones; si fallan, el original
uv run syn eval news --gold eval/news/labels.csv [--pairs eval/news/pairs.csv]   # macro F1 del LLM y del baseline (grupo eval)
uv run syn facts --provider groq [--limit 40] [--until HH:MM] # hechos verificados de los estudios a resumir (lee el almacén)
uv run syn write --provider groq [--limit 40] [--until HH:MM] # resumen EN → ES con comprobaciones; si falla, texto de respaldo
uv run syn judge --provider groq [--limit 40] [--until HH:MM] # juez de otra familia (gpt-oss-120b): sin su aprobado no se publica
uv run syn recheck                        # vuelve a comprobar los textos en español que fallaron, sin LLM
uv run syn weekly --provider groq [--week 2026-W45]   # resumen semanal: misma cadena, comprobaciones y juez
uv run syn build                          # dbt build: modelos + tests (desde la Fase 1)
uv run syn figures                        # Figura 1 de Última hora desde el bucket abierto de PMC (WebP a data/cache/)
uv run syn mirror export --out DIR        # marts a Parquet para el espejo semanal en BigQuery (tope 1 GiB)
uv run syn mirror record --dir DIR [--stored S]   # anota filas y bytes en mirror/bigquery.jsonl
uv run syn review queue --out Q                 # cola del día: resúmenes por muestreo (peor español primero), tope 40/10
uv run syn review queue --out Q --run DIR       # … más los textos de una ejecución pasada (p. ej. runs/18/qwen9b)
uv run syn review page --queue Q --out DIR      # páginas de revisión de Sofía (pública y privada)
uv run syn review round --queue Q --out DIR     # siguiente ronda: aplica su registro y deja lo pendiente
uv run syn review intake --event E (--queue Q | --queue-dir D) --reviewer LOGIN --reply R [--efetch X]   # lee un Issue suyo (exit 2: espera fuente)
SYN_DATA_DIR=/tmp/syn-ci uv run python scripts/seed_fixture_data.py   # fixtures como si vinieran de las fuentes
SYN_DATA_DIR=/tmp/syn-ci uv run syn build --as-of 2026-11-09          # dbt sobre esas fixtures (como la CI)
uv run syn site && uv run syn site --check
scripts/gpu_batch.sh RUN_DIR CMD...       # lote LLM local: systemd-inhibit, vitales de la GPU a CSV, para a 85 °C
```

Actualiza esta lista cada vez que se añada un comando.

## Convenciones

- Código, identificadores, comentarios, docstrings y mensajes de commit en inglés. La documentación va primero en español; el README también en inglés.
- Commits con Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Ruff con la configuración de `pyproject.toml` (líneas de 100 caracteres).
- Los comandos `syn` son idempotentes: ejecutarlos dos veces deja el mismo resultado.
- Fechas en UTC y en formato ISO 8601.
- Cada decisión de arquitectura lleva un ADR breve en `docs/adr/` (contexto, decisión, alternativas, consecuencias y pruebas). Cada fase cerrada lleva su `docs/fases/fase-N.md`.

## Una tarea está hecha cuando

- pasan pytest y ruff, `syn build` (si aplica) y `syn site --check` (si toca la web);
- lo nuevo tiene tests con fixtures y sin red;
- `SCOPE.md` está al día (casilla y registro de cambios);
- Aday ha visto el resultado;
- lo que tiene que aprobar Sofía está en su cola de revisión, no publicado.

## Nunca

- Hacer push, crear o borrar repositorios, ni tocar secretos, Pages o ajustes de GitHub sin confirmación de Aday.
- Añadir servicios de pago, ni dependencias nuevas sin explicar para qué son.
- Publicar contenido de salud sin revisar, o texto generado que no haya pasado las comprobaciones.
- Inventar datos, cifras o fuentes para rellenar un hueco. Si falta un dato, se deja vacío y se avisa.
