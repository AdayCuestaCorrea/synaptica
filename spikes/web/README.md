# Maqueta de la web (Fase 1, antes de los pasos 21–24 y 26)

Estilo elegido: **N «Noche»** (SCOPE v79), oscuro por defecto y claro si se pide, con la estructura del boceto de Sofía (ronda 3, SCOPE v78). Las rondas 1 (A, B, C) y 2 (hub en tres estilos) y los estilos G y L de la ronda 3 se borraron en v79; siguen en la historia de git (commits `4d7b959`, `fa1cc8c` y `658d966`).

Datos reales, en español e inglés; nada se carga de otro dominio. Los huecos y las propuestas llevan una etiqueta que enlaza a la lista del final de cada página.

## La portada (un solo scroll)

1. Cabecera: Inicio, Neuro News, Cómo evaluamos, Glosario, Sobre nosotros y el buscador (en el móvil, el menú en dos líneas).
2. «Tu portal de neurociencia», con el cerebro humano del visor y una neurona dibujada.
3. Las seis secciones en 3 × 2: Neuro Atlas enlaza al prototipo de S3; las demás dicen en qué fase llegan.
4. «Hoy»: noticia destacada (figura, título, resumen), tres titulares con sus señales, el dato curioso y el enlace al resumen semanal.
5. «Explora por temas»: Memoria, Adicción, Neurodegeneración, Neuroinflamación, Sueño y Emoción, cada uno con su página (regla de la maqueta: palabras del título).

Además: Neuro News (pestañas, filtros, «Ver más»), página de cada estudio, «Cómo evaluamos», resumen semanal, «Sobre nosotros» (borrador), «Buscar», una página por tema y el «Glosario».

## Glosario (`glossary.py`, `v3/styles/glossary.js`, `v3/templates/glossary.html.j2`)

Copiado y adaptado de Paleo Atlas (`src/paleo/site/glossary.py`, `site/static/glossary.js`, `site/templates/glossary.html.j2`; cada archivo lo dice en su cabecera).

- Términos: los 17 de ejemplo de `docs/propuesta.md` (significado y definición, solo en español, por revisar). Las formas que se buscan en los textos están en `data/glossary_forms.csv`: la sigla, que solo coincide con sus mayúsculas exactas (`DA` es dopamina y «da» es un verbo), y su nombre completo en español o en inglés, sin distinguir mayúsculas. Las formas salen solo de la tabla de la propuesta.
- Se marca la primera aparición de cada término en la página: título y resumen (verificado o de respaldo) de la página de cada estudio, y resumen de la destacada de «Hoy». Nunca dentro de un enlace (los títulos de las tarjetas ya lo son).
- Sin JavaScript, el término es un enlace a su entrada. Con JavaScript, al pasar el ratón, enfocarlo o tocarlo se abre una ventanita con la definición; si el puntero se queda, se fija y los términos de dentro abren otra encima.
- En inglés no hay definiciones: el término se marca igual, y la ventanita y la entrada dicen «Definition pending», con la etiqueta de hueco.
- Hoy se marcan 10 apariciones en 8 páginas por idioma: Alzheimer, Parkinson, corteza prefrontal, fMRI, GFAP y DREADDs.

## Regenerar

```sh
# 1. Datos reales (almacén construido desde raw/ con `syn build`; peticiones cacheadas en data/sources/)
SYN_DATA_DIR=<scratch> uv run python spikes/web/collect.py --warehouse <scratch>/warehouse.duckdb
# 2. Imágenes (red: el bucket de PMC; la caché, data/sources/images/, la ignora git)
uv run python spikes/web/images.py
# 3. Páginas (Jinja2), ES y EN
uv run python spikes/web/build3.py
# 4. Contraste WCAG de cada par de colores, claro y oscuro
uv run python spikes/web/contrast.py
# Ver
python -m http.server 8771 --bind 127.0.0.1 --directory spikes/web
```

`build.py` y `build2.py` ya no generan páginas: guardan las reglas de cada estudio (señales, texto, licencia) y los textos en los dos idiomas que usa `build3.py`.

## De dónde sale cada dato

- Estudios y noticias: el almacén del 2026-11-12 (`dim_study`, `fct_news_item`).
- Resúmenes verificados: S5, pareja de D4 (`spikes/s5/results/run_groq-qwen-qwen3.8-27b-groq-openai-gpt-oss-120b.json`), solo los que pasaron las comprobaciones y el juez; el resto, `synaptica.narrative.fallback`.
- Ejemplos de retractado y corregido: avisos reales de nuestro lote de Crossref y metadatos de la API de Crossref.
- Dato curioso (propuesta del paso 26): una cifra calculada del almacén, sin LLM.
- Selección para la maqueta: de los estudios «sin dato» de especie solo entran los que llevan un término de neuro en el título, porque el ruido lo quita el paso 14a, que aún no se ha ejecutado.

## Imágenes (`img/`, autoalojadas; autor y licencia en `data/images.json` y visibles en la página)

- **Figuras de los estudios**: solo artículos del subconjunto de acceso abierto de PMC con licencia CC, desde el bucket público de NLM en AWS (`pmc-oa-opendata`), que da la licencia de cada artículo. Resumen gráfico si lo hay; si no, la primera figura, redimensionada y sin recortar. Nunca de Nature, Science y Cell ni de los medios.
- **Neuro Atlas**: capturas de nuestro visor de S3, una por atlas (Waxholm, CC BY 4.0; Julich-Brain, CC BY-NC-SA 4.0), con la atribución de su `licence.json`.
- **Ilustraciones**: dibujos propios en SVG (`v3/templates/art/`, CC BY-SA 4.0), en línea para que tomen los colores del modo claro u oscuro.

## Fuentes tipográficas (`fonts/`)

Atkinson Hyperlegible, © Braille Institute of America, SIL Open Font License 1.1 (`fonts/OFL-atkinson-hyperlegible.txt`). Autoalojada, subconjunto latino en woff2, copiada del paquete de Fontsource `@fontsource/atkinson-hyperlegible@5.2.5`.
