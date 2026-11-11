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
- Cada estudio muestra sus señales: revisado por pares o preprint, en humanos o en animales, retractado o corregido.

**Textos generados con LLM.**
- Pasan las mismas comprobaciones que en Paleo Atlas: cada frase cita su fuente, las cifras y los nombres coinciden con ella, y nunca hay 8 o más palabras seguidas copiadas.
- Un texto que no pasa no se publica; en su lugar se muestra el texto de respaldo construido con datos.
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
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run syn build                          # dbt build: modelos + tests (desde la Fase 1)
uv run syn site && uv run syn site --check
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
