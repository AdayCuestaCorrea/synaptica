# Maquetas de la web (Fase 1, antes de los pasos 21–24 y 26)

Tres direcciones para elegir (SCOPE v76), con datos reales y en español e inglés:

- **A · Gaceta** (`a/`): un periódico científico. Newsreader + sans del sistema.
- **B · Fluorescencia** (`b/`): un instrumento de laboratorio. Atkinson Hyperlegible + mono del sistema.
- **C · Calma** (`c/`): la casa del visor de S3. Fuentes del sistema.

Ninguna carga nada de otro dominio. Los huecos y las propuestas van marcados en amarillo con borde discontinuo.

## Regenerar

```sh
# 1. Datos reales (almacén construido desde raw/ con `syn build`; solo 3 peticiones, cacheadas en data/sources/)
SYN_DATA_DIR=<scratch> uv run python spikes/web/collect.py --warehouse <scratch>/warehouse.duckdb
# 2. Páginas (Jinja2) de las tres maquetas, ES y EN
uv run python spikes/web/build.py
# 3. Contraste WCAG de cada par de colores, claro y oscuro
uv run python spikes/web/contrast.py
# Ver
python -m http.server 8771 --bind 127.0.0.1 --directory spikes/web
```

## Ronda 2 (`v2/`, SCOPE v77)

Aday eligió la opción mixta: la portada es un *hub* con las noticias de hoy en la primera pantalla (una destacada, cuatro titulares, el dato curioso y el resumen semanal) y debajo las secciones (Neuro Atlas como avance, Neuro News, Resumen semanal, Cómo evaluamos). Neuro News completa vive en su página (`noticias.html` / `news.html`), en una columna, con pestañas (Última hora, Nature · Science · Cell, Clásicos, En los medios), filtros y «Ver más» de 8 en 8. Las tarjetas ya no llevan resumen: solo titular, revista, fecha y las tres señales. Los huecos se marcan con una etiqueta corta que enlaza a la lista del final de cada página.

Una sola plantilla (`v2/templates/`) y tres estilos (`v2/styles/{g,n,l}.css` sobre `base.css`):

- **G · Gaceta**: la A ordenada. Claro, Newsreader, azul de Prusia; Cajal impreso como tinta.
- **N · Noche**: oscuro por defecto (claro si se pide), Atkinson Hyperlegible, un acento turquesa; Cajal en líneas de luz.
- **L · Lámina**: la paleta «calma» del visor de S3, tarjetas teñidas por sección y Cajal en láminas grandes; fuentes del sistema.

Cada estilo lleva una propuesta distinta para el dato curioso (G: frase verificada; N: cifra del almacén; L: efeméride de Wikidata).

```sh
uv run python spikes/web/images.py    # imágenes (red: Commons y el bucket de PMC; caché ignorada por git)
uv run python spikes/web/build2.py    # 390 páginas
uv run python spikes/web/contrast2.py # contraste de cada par, claro y oscuro
```

Imágenes (`v2/img/`, autoalojadas; autor y licencia en `data/images.json` y visibles en la página):

- **Dibujos de Santiago Ramón y Cajal**: Wikimedia Commons, categoría «Scientific works by Santiago Ramón y Cajal», dominio público según Commons. Pasados a grises (papel a blanco), sin otro cambio.
- **Figuras de los estudios**: solo artículos del subconjunto de acceso abierto de PMC con licencia CC, desde el bucket público de NLM en AWS (`pmc-oa-opendata`), que da la licencia de cada artículo. Se usa el resumen gráfico si lo hay y si no la primera figura, redimensionada y sin recortar (vale también para las licencias ND). Nunca de Nature, Science y Cell (solo metadatos y enlaces) ni de los medios (sus imágenes no tienen licencia clara). El texto completo se descarga solo a la caché, para leer el número de la figura, y no se publica.
- **Neuro Atlas**: capturas de nuestro visor de S3 con Brave sin interfaz, una imagen por atlas (Waxholm, CC BY 4.0, y Julich-Brain, CC BY-NC-SA 4.0, nunca en la misma imagen), con la atribución que S3 guardó en `licence.json`.

## De dónde sale cada dato

- Estudios y noticias: el almacén del 2026-11-12 (`dim_study`, `fct_news_item`).
- Resúmenes verificados: S5, pareja de D4 (`spikes/s5/results/run_groq-qwen-qwen3.8-27b-groq-openai-gpt-oss-120b.json`), solo los que pasaron las comprobaciones y el juez; el resto, `synaptica.narrative.fallback`.
- Ejemplos de retractado y corregido: avisos reales de nuestro lote de Crossref y metadatos de la API de Crossref.
- Efeméride de C: Wikidata (CC0).
- Selección para la maqueta: de los estudios «sin dato» de especie solo entran los que llevan un término de neuro en el título, porque el ruido lo quita el paso 14a, que aún no se ha ejecutado.

## Fuentes tipográficas (`fonts/`)

Autoalojadas, subconjunto latino en woff2, copiadas de los paquetes de Fontsource (`@fontsource-variable/newsreader@5.2.5`, `@fontsource/atkinson-hyperlegible@5.2.5`):

- **Newsreader**: © The Newsreader Project Authors (Production Type). SIL Open Font License 1.1 (`fonts/OFL-newsreader.txt`).
- **Atkinson Hyperlegible**: © Braille Institute of America. SIL Open Font License 1.1 (`fonts/OFL-atkinson-hyperlegible.txt`).
