# Fuentes de datos

Resultado del spike **S1** (`SCOPE.md` §5 y §7). Para cada fuente: cómo se accede, sus límites, si hace falta clave, su licencia y lo que se midió. Medido el **2026-11-09** (UTC) con los scripts de [`spikes/s1/`](../spikes/s1/). Las respuestas guardadas están en [`tests/fixtures/`](../tests/fixtures/).

**Leyenda.** *Medido*: comprobado con una petición real (cabeceras o respuesta). *Documentado*: lo dice la documentación oficial. *Por confirmar*: no lo he podido verificar todavía; no se da por bueno.

## Reglas comunes

- Todas las peticiones llevan el User-Agent `synaptica-bot/<versión> (https://github.com/AdayCuestaCorrea/synaptica; adaycuestacorrea@gmail.com)` (`synaptica.config.USER_AGENT`). Donde la API lo admite, también `mailto` o `email`.
- Las peticiones se hacen en serie, nunca en paralelo, con una pausa entre ellas.
- **Las fixtures no guardan texto de los editores.** Abstracts, descripciones de los RSS y cuerpos de artículo se sustituyen por `[REDACTED in fixture…]`, porque el repositorio es público y ese texto no es nuestro. También se quitan las listas voluminosas que no se usan, como las referencias de Crossref, y se deja solo su recuento. Los textos completos que necesite la Fase 1 para escribir los resúmenes irán a una caché sin versionar, como en Paleo.

## Fase 1 — Neuro News

| Fuente | Acceso | Límites | Clave | Licencia | Medido el 2026-11-09 |
|---|---|---|---|---|---|
| **PubMed** (E-utilities) | `esearch` → `esummary` (JSON) / `efetch` (XML) | 10 peticiones/s con clave y 3 sin ella. *Medido* con la cabecera `x-ratelimit-limit: 10` | `NCBI_API_KEY`, opcional y ya configurada | Metadatos de la NLM de uso libre; **los abstracts tienen el copyright de cada editor** | Consulta amplia de neuro (MeSH + palabras en título y abstract): **785 registros en 1 día y 3434 en 7**. Tipos de publicación y MeSH presentes; los registros nuevos aún no tienen MeSH |
| **Europe PMC** | REST `search` (JSON, `resultType=core`); `/{PMCID}/fullTextXML` | 10 peticiones/s por IP según el equipo de Europe PMC en su foro; no envía cabeceras de límite. *Por confirmar en la documentación oficial* | No | Metadatos libres; el texto completo, con la licencia de cada artículo (vistas: CC BY y CC BY-NC-ND) | 1742 registros de neuro en 7 días, de ellos 189 en acceso abierto. El texto completo responde (141 KB, no guardado) |
| **bioRxiv / medRxiv** | `api.biorxiv.org/details/{server}/{desde}/{hasta}/{cursor}?category=…` | No se publica un límite (*por confirmar*). **Es lenta:** unos 13 s por petición, y una dio timeout a los 30 s. Páginas de 30 | No | La de cada preprint, que viene en el campo `license`: `cc_by`, `cc_by_nc`, `cc_by_nd`, `cc_by_nc_nd`, `cc0` y `cc_no` (sin reutilización) | bioRxiv `neuroscience`: **384 en 7 días**. medRxiv `neurology`: 51. medRxiv `psychiatry_and_clinical_psychology`: 30, que coincide justo con el tamaño de página; hay que confirmarlo paginando |
| **Nature, Science, Cell** y hermanas | RSS público por revista | Sin límite publicado; una petición al día basta | No | Términos de cada editor: **solo título, autores, DOI y enlace** (CLAUDE.md) | **Los 7 RSS responden:** Nature (75 items), Nature Neuroscience (8), Nature Reviews Neuroscience (8), Science (45), Science Advances (81), Cell (25), Neuron (14). Todos traen DOI. El riesgo de §9 queda descartado |
| ↳ alternativa: **Crossref por ISSN** | `api.crossref.org/journals/{ISSN}/works` | Igual que Crossref (abajo) | No | Igual que Crossref | Funciona. Hay que usar el **ISSN impreso para Cell Press** (Cell 0092-8674, Neuron 0896-6273); el electrónico da 404. En 14 días: Nature 202, Science 92, Science Advances 162, Nature Neuroscience 16, Cell 7, Neuron 5 |
| **ScienceDaily** (Neuroscience) | RSS `rss/mind_brain/neuroscience.xml` | Sin límite publicado | No | Términos de sus RSS: texto sin modificar y con atribución (los mismos que en Paleo) | 61 items, 51 con una palabra de neuro en el título |
| **The Conversation** | Atom por tema: EN `topics/neuroscience-427`; ES `es/topics/neurociencia-55189` y `es/topics/cerebro-54660` | Sin límite publicado | No | CC BY-ND 4.0 (como en Paleo) | 25 items por feed; 16, 11 y 15 con una palabra de neuro en el título. **Ojo:** los ID de tema que adiviné llevaban a otros temas («Birth control», «Property»). Los buenos salieron del buscador de la web |
| **SINC** | RSS `agenciasinc.es/feed/{sección}` | — | No | CC BY 4.0 (como en Paleo) | **Caído durante la prueba:** 503 del CDN, con «Sick Healthcheck» del servidor de origen; no es un bloqueo. Falta repetirlo y elegir la sección (Salud o Noticias) |
| **Crossref** | `works/{DOI}`; `works?filter=update-type:…` | Con `mailto`: **10 peticiones/s y 3 concurrentes** por DOI, pero **3/s en las consultas de lista**. *Medido* con las cabeceras `x-rate-limit-*` | No | Metadatos sin restricciones | `works/{DOI}` trae `updated-by`, **con los datos de Retraction Watch incluidos**. Lesné et al. 2006 (10.1038/nature04533) aparece como retractado por el editor y por Retraction Watch, y con una expresión de preocupación. Avisos de los últimos 30 días, en todas las disciplinas: 5918 retractaciones y 3814 correcciones |
| **OpenAlex** | `works?filter=primary_topic.field.id:28,…&sort=cited_by_count:desc` | **Sin clave:** 10 peticiones/s y unas 1000 consultas de lista al día (*medido* con la cabecera `x-ratelimit-limit: 1000`). **Con la clave gratuita:** 30/s y 10 veces más presupuesto. `search=` cuesta 10 veces más que `filter=` (*documentado*) | No hace falta para la propuesta semanal de Clásicos; existe una clave gratuita sin tarjeta | CC0 | El campo 28 es Neuroscience (comprobado en la respuesta): 103 445 trabajos de 2016; el más citado tiene 8951 citas |

## Fases 2–4

| Fuente | Acceso | Límites | Clave | Licencia | Medido el 2026-11-09 |
|---|---|---|---|---|---|
| **Wikipedia** (EN/ES) | Action API (`action=query`, `maxlag=5`) | Etiqueta de Wikimedia: User-Agent con contacto, peticiones en serie y `maxlag` (como en Paleo) | No | CC BY-SA 4.0, compatible con nuestros textos (CC BY-SA 4.0) | «Hippocampus» y «Hipocampo (anatomía)» resuelven al mismo elemento de Wikidata, Q48360 |
| **Wikidata** | `wbsearchentities`, `wbgetentities` (y SPARQL, por probar) | Igual que Wikipedia | No | CC0 | Parkinson = Q11085, con etiquetas en EN y ES y 97 propiedades. **No tiene P927 (localización anatómica)**: la relación enfermedad → región puede tener huecos, y hay que medirla en la Fase 2 antes de contar con ella |
| **Wikimedia Commons** | `generator=search` + `imageinfo` con `extmetadata` | Igual que Wikipedia | No | La de cada archivo, que viene en `LicenseShortName` y `Artist` | 10 imágenes de «hippocampus brain»: CC BY-SA 2.1–4.0, CC BY 4.0 y CC0 |
| **ClinicalTrials.gov** | API v2 `studies` con `fields=` | *Por confirmar* | No | Datos del Gobierno de EE. UU. (*por confirmar los términos*) | Alzheimer, reclutando en España: **37 ensayos** |
| **nobelprize.org** | API 2.1 `nobelPrizes?nobelPrizeYear=…&nobelPrizeCategory=med` | *Por confirmar* | No | *Por confirmar* | El Nobel de Medicina de 2026 (Deisseroth, Hegemann, Nagel; «light-gated ion channels and optogenetics») coincide con la tabla de la propuesta. Es una API propia, así que no hace falta Wikidata para los Nobel |
| **Julich-Brain, Waxholm, Allen, BrainGlobe** | — | — | — | — | Se comprueban en el **spike S3** (visor 3D), donde se descargan de verdad |

## Qué cambia para el diseño

- **Volumen.** PubMed da entre 500 y 800 registros de neuro al día con una consulta amplia. Ni el LLM ni Sofía pueden con eso entero: la Fase 1 necesita un filtro previo (consulta más estrecha, tipos de publicación, revistas) antes de clasificar. Para **D6**: el volumen diario cabe de sobra en las APIs. Una carga histórica solo tendría sentido para los Clásicos, y OpenAlex ya ordena por citas, así que **no hay motivo medido para Databricks**.
- **Nature, Science y Cell no necesitan Crossref:** los RSS bastan, y Crossref queda como respaldo.
- **Retractaciones:** una consulta por DOI en Crossref da la señal de retractación y de corrección, con Retraction Watch incluido.
- **Clásicos:** OpenAlex sin clave, solo con `filter` (nunca `search`).

## Pendiente

- [ ] SINC: repetir cuando vuelva y elegir la sección.
- [ ] Confirmar los límites de bioRxiv, Europe PMC (documentación oficial), ClinicalTrials.gov y nobelprize.org, y las licencias de los dos últimos.
- [ ] medRxiv: confirmar con paginación el volumen de psiquiatría.
- [ ] Atlas: en S3.
