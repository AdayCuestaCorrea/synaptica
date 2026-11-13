[English](README.md) · **Español**

# SYNAPTICA — tu portal de neurociencia

Web gratuita de neurociencia en español e inglés que se actualiza sola cada día: noticias científicas con resúmenes verificados y secciones para aprender cómo funciona el cerebro. La hacen Aday Cuesta Correa (desarrollo) y Sofía (revisión científica).

**Web:** https://adaycuestacorrea.github.io/synaptica/ (en español e inglés, en claro y oscuro).

**Estado:** la Fase 1 (la base) está hecha y en marcha: Neuro News se actualiza sola cada día desde el 2026-11-13. La fase se cierra tras 14 días de ejecuciones diarias sin intervención. El plan y su orden están en [`SCOPE.md`](SCOPE.md).

## Cómo es un día

Cada mañana corre un workflow de GitHub Actions ([`pipeline.yml`](.github/workflows/pipeline.yml)):

1. **Ingesta** de lo nuevo en PubMed, Crossref (retractaciones y correcciones), Europe PMC, bioRxiv y medRxiv, los RSS de Nature · Science · Cell, tres medios de divulgación y OpenAlex. A git solo van metadatos; los abstracts se quedan en una caché privada.
2. **Clasificación y resúmenes** con LLM gratuitos en Groq: cada estudio recibe un tipo, unos hechos verificados, un resumen en inglés y su adaptación al español. Cada frase cita sus hechos, las cifras y los nombres coinciden con la fuente, nunca hay 8 palabras seguidas copiadas y un juez de otra familia de modelos tiene que aprobarlo. Lo que no pasa muestra un texto de respaldo construido solo con datos.
3. **Reconstrucción** del almacén DuckDB con dbt (con sus tests) y de la web estática, con `syn site --check` (enlaces, hreflang, aviso médico en cada página y señales en cada estudio).
4. **Revisión:** una muestra de los resúmenes va a una página donde la neurocientífica los aprueba, corrige o rechaza desde el navegador; sus decisiones vuelven como Issues de GitHub y se aplican solas.
5. **Commit** de los datos en la rama `data` y publicación en GitHub Pages; una vez por semana, los marts se copian al sandbox de BigQuery.

## Qué es y qué será

- **Neuro News** cada día desde fuentes abiertas (PubMed, Europe PMC, bioRxiv, metadatos de Nature · Science · Cell, medios de divulgación); cada resumen se comprueba contra su fuente antes de publicarse.
- **Neuro Atlas** (cerebro humano y de rata en 3D), **Neuro Lab**, **Neuro Glossary**, **Neuro Learn**, **Neuro Diseases**, **Neuro History** y **Neuro Experiments**.
- **No es consejo médico.** El contenido de salud lo revisa una neurocientífica antes de publicarse.
- **0 € al mes:** GitHub Actions, GitHub Pages, planes gratuitos de APIs y modelos locales.

Reutiliza el motor de [Paleo Atlas](https://github.com/AdayCuestaCorrea/paleo-atlas): el estado vive en git, el almacén se reconstruye en cada ejecución, un comando por paso, y los textos del LLM citan sus fuentes y pasan comprobaciones automáticas.

## Ejecutarlo en local

```sh
uv sync
uv run syn --help
uv run syn doctor          # comprueba el entorno
uv run pytest              # tests, nunca usan la red
uv run ruff check . && uv run ruff format --check .
```

## Documentación

- [`SCOPE.md`](SCOPE.md): alcance, fases, decisiones y registro de cambios.
- [`docs/propuesta.md`](docs/propuesta.md): el producto tal como se aprobó.
- [`docs/adr/`](docs/adr/README.md): decisiones de arquitectura.
- [`docs/fases/`](docs/fases/README.md): un documento por fase cerrada.

## Licencia

Código: [AGPL-3.0](LICENSE) · Textos propios: [CC BY-SA 4.0](LICENSE-CONTENT.md) · Los datos, imágenes y modelos 3D de terceros conservan su propia licencia.
