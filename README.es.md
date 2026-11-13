[English](README.md) · **Español**

# SYNAPTICA — tu portal de neurociencia

Web gratuita de neurociencia en español e inglés que se actualiza sola cada día: noticias científicas con resúmenes verificados y secciones para aprender cómo funciona el cerebro. La hacen Aday Cuesta Correa (desarrollo) y Sofía (revisión científica).

**Estado:** Fase 0 (cimientos) cerrada el 2026-11-13 ([resumen](docs/fases/fase-0.md)); empieza la Fase 1 (la base). Todavía no hay web. El plan y su orden están en [`SCOPE.md`](SCOPE.md).

## Qué será

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
