# Spike S4 · Flujo de revisión de Sofía (decisión D5)

Plan aprobado por Aday el 2026-11-11. Resultado: el ADR `docs/adr/0005-revision.md`. D5 sigue abierta hasta que Aday decida con los resultados de la prueba con Sofía.

## Objetivo
Que las decisiones de Sofía lleguen al repositorio como datos (rama `data`) sin que ella use terminal, git ni YAML, a 0 €, sin secretos en una web estática pública y en menos de 1 h al día. En S5 copió sus respuestas y se las mandó a Aday a mano: la interfaz funcionó, pero el camino de vuelta no escala, y dejó dos huecos que hubo que interpretar ([ADR D4](../../docs/adr/0004-llm.md#revisión-de-sofía-2026-11-10)).

## Qué revisa Sofía
Volúmenes **estimados**: ninguno está fijado todavía.

| Qué | Tipo de decisión | Fase | Frecuencia | Volumen ≈ | ¿Bloquea? |
|---|---|---|---|---|---|
| Fichas de Neuro Diseases | aprobar, corregir o rechazar (ES + EN) | 3 | una vez, y otra si cambia el borrador | 15–30 fichas | **Sí** (`reviewed_by`, `reviewed_at`) |
| Textos de las zonas del atlas | ídem | 2 | una vez; primero las de su investigación (§9) | 20–40 al principio | No |
| Región → términos de búsqueda | revisar sinónimos | 2 | una vez | las mismas | No |
| Tabla rata ↔ humano | **poner y cambiar** el grado (clara, parcial o discutida) y la nota, con historial | 2 | una vez y algún cambio | 20–50 pares | No: sin grado no hay vista comparada |
| Técnicas de Neuro Lab | revisar borrador | 2 | una vez | ≈ 11 | No |
| Glosario | revisar definiciones y **proponer siglas nuevas** | 2 | una vez y altas sueltas | 100–200 términos | No |
| Neuro Learn | elegir temas y revisar borradores | 3 | una vez | 10–20 y neuromitos | No |
| Clásicos | elegir entre candidatos | 1 | **cada semana** | 5–10 candidatos | Solo los Clásicos |
| Temas o tipos de noticia que sobran | activar o desactivar; marcar una noticia | 1 | una vez y ajustes | ≈ 10 categorías | No |
| Etiquetas del clasificador (objetivo §2) | etiquetar una muestra | 1 | una vez, en varios días | ≈ 300 | No |
| Hitos, experimentos y vídeos | proponer | 4 | de vez en cuando | pocos | No |
| Resúmenes de noticias ya publicados | revisión opcional, ordenada por la nota `spanish_natural` del juez ([ADR D4](../../docs/adr/0004-llm.md)) | 1 | cuando tenga tiempo | — | No |

Consecuencias: el flujo no es solo «aprobar o rechazar»: hay valores cerrados, textos corregidos, elegir varios y **altas nuevas**. El día a día es ligero (Clásicos, unos 10 min a la semana); la carga llega en picos al empezar cada fase, así que la cola va priorizada (Neuro Diseases primero) y se puede dejar a medias.

## Opciones comparadas

| | A · Editar en github.com | B · Formulario de Issues | **C · Página generada + envío como Issue** | D · Google Sheets | E · CMS (Decap) o Worker |
|---|---|---|---|---|---|
| Sin git ni YAML | **No** | Sí | Sí | Sí | Sí |
| Cuenta | GitHub, colaboradora | GitHub (no colaboradora: el repo es público) | GitHub, no colaboradora | Google | GitHub, colaboradora |
| Quién y cuándo | commit | autor y fecha del Issue, autenticados | ídem | historial de la hoja (débil por API) | commit |
| Ve el texto como quedará | No | No | **Sí** (la interfaz de S5) | Mal con textos largos | Sí |
| Encaje con Actions | push o PR | `on: issues` → commit en `data` | ídem | lectura diaria con la WIF de S2 | push |
| Secretos en la web | No | No | No (el usuario autorizado es una *variable* del repo) | No | El proxy OAuth necesita uno |
| Contras | Incumple los requisitos | Un Issue por elemento; elegir o poner grados es incómodo | Issues públicos; **límite de la URL sin medir** | Sincronización en dos sentidos, otra plataforma, sin vista previa | Más servicios y autenticación |

Descartadas además: copiar y enviar a mano (S5; no escala y `reviewed_by` saldría de Aday), un token pegado en la página (gestión técnica para Sofía) y el correo (leerlo desde Actions pide un token OAuth).

**Recomendación: C.** D queda de reserva si C falla en la prueba.

## Decisiones de Aday (2026-11-11)
1. **Cuenta de GitHub para Sofía**, sin ser colaboradora durante el proyecto (D9 no cambia); quizá se la añada al final.
2. **Neuro Diseases fuera de lo público:** su página se genera como archivo y Aday se la manda; la respuesta vuelve por el Issue (solo el hash de la versión aprobada y, si corrige, su texto). Sin cifrado ni dependencias nuevas.
3. **Issues públicos:** las decisiones van en el Issue; la nota es opcional y la página avisa de que será pública. Lo privado, por WhatsApp o correo.
4. **Correcciones de Sofía:** su versión pasa otra vez las comprobaciones mecánicas (cita por frase, cifras y nombres, 8 palabras copiadas) y el juez **solo como aviso**, que nunca bloquea. Si una comprobación falla, la decisión no se aplica y el texto vuelve a su cola con el aviso; ella corrige o marca «lo mantengo» con un motivo, y queda registrado. Amplía la regla de CLAUDE.md, que hoy solo habla de textos generados; la línea nueva se escribe con el ADR si Aday la confirma.

## Diseño
- **Registro de solo añadir** en la rama `data`: `review/decisions.jsonl`, una línea por decisión: `item_type`, `item_id`, `content_sha256`, `action`, `payload`, `note`, `reviewed_by`, `reviewed_at`, `source` (número de Issue). El estado actual es la última decisión por elemento; el historial (por ejemplo, de los grados) no se pierde.
- **La aprobación se ata al hash del contenido:** si el borrador cambia, caduca y vuelve a la cola. Así se cumple la regla de Neuro Diseases sin vigilarla a mano.
- **`reviewed_by` y `reviewed_at`** salen del autor y de la fecha del Issue (UTC), no de un campo que se pueda rellenar.
- **Recepción:** un workflow `on: issues` comprueba que el autor es el de la variable del repo, valida el esquema y los hashes contra la cola, añade las decisiones al registro, comenta el resultado en el Issue y lo cierra. Comparte `concurrency` con el pipeline diario para no pisar la rama `data`.
- **De Paleo Atlas** (`scripts/label_news.py`, `review_glossary.py`, `merge_data.py`): muestra fija con semilla para retomar la sesión, «la propuesta del LLM no cuenta hasta que una persona la confirma», modo ciego y unión por clave en la rama `data`. Se copia y se adapta, citando el origen.

## Pasos
Un commit por paso; cada uno con pytest y ruff en verde, y su línea en el §11 de SCOPE.

0. ✅ **Plan:** este documento.
1. ✅ **Modelo y fixtures:** `ReviewItem` y `Decision` (pydantic); cola de ejemplo en `tests/fixtures/review/` con material existente (resúmenes de S5, pares de `spikes/s3/site/data/equivalencias.json` en solo lectura, siglas de la propuesta). La ficha de Neuro Diseases de ejemplo se marca como texto de prueba: no se inventan contenidos de salud.
2. ✅ **Página de revisión:** `spikes/s4/review_page.py` y su plantilla, a partir de las de S5. Una sección por tipo de decisión, borradores en `localStorage`, aviso de nota pública y la variante «archivo local» para Neuro Diseases. Tests: se genera con las fixtures y no lleva abstracts.
3. ✅ **Envío** (falta el envío real de punta a punta, ver [resultados](results/README.md)): la página codifica las decisiones en un bloque legible y abre el Issue ya relleno. Tests de ida y vuelta. Borrador del formulario `revision.yml` **dentro de `spikes/s4/`**: activarlo en `.github/` necesita la confirmación de Aday. Medición manual del límite de la URL y del relleno de campos (`?template=…&<id>=…`), con los resultados en `results/`.
4. **Recepción:** `spikes/s4/intake.py`: autor, esquema, hashes, comprobaciones mecánicas de los textos corregidos, juez como aviso, estado «vuelve a la cola» y «lo mantengo». Fixtures de eventos de Issue: válido, autor ajeno, hash caducado y mal formado. Borrador de `review-intake.yml`, sin activar.
5. **Aplicar:** del registro al estado actual. Tests: una ficha sin aprobar o con el hash caducado no se publica; un cambio de grado conserva el anterior.
6. **Prueba con Sofía preparada**, para cuando cierre S3: guion con tareas cronometradas (aprobar una ficha, corregir un texto, poner grado a dos pares, elegir Clásicos, desactivar un tema, añadir una sigla y enviar), creación de su cuenta de GitHub con Aday y qué se mide (tiempo, errores, dudas, si el Issue llega bien).
7. **Resultados y borrador del ADR** `docs/adr/0005-revision.md`. D5 sigue abierta hasta que decida Aday.

## Resultado de los pasos
- **Paso 1** (`models.py`, `make_fixtures.py`, `tests/`): `ReviewItem` con cinco formas de contenido (texto ES + EN con citas, términos de búsqueda, par rata ↔ humano, candidatos a Clásicos y tema activable) y `Decision` con nueve acciones, cada una con su `payload` validado. El hash cubre el tipo, el ID y el contenido, no el título. `check_against` detecta elementos desconocidos, hashes caducados y Clásicos elegidos fuera de los candidatos o por encima del máximo. Fixtures en `tests/fixtures/review/` generadas solo con material del repositorio (resumen de S5, glosario de la propuesta, pares de S3, OpenAlex); la ficha de Neuro Diseases es un texto de prueba marcado. Tests: `uv run --group spike-s4 pytest spikes/s4/tests` (la CI normal no instala el grupo).
- **Paso 2** (`review_page.py`, `review/template.html`): una página por variante, `revision.html` (pública, 12 elementos) y `revision-privada.html` (solo Neuro Diseases), sin mezclar nunca. Ordenada por prioridad: Neuro Diseases, Clásicos (caducan cada semana), grados rata ↔ humano, textos, temas y, al final, los resúmenes publicados. Cada respuesta se guarda en el navegador atada al hash: si el borrador cambia, la respuesta vieja no se reutiliza. Corregir sin cambiar nada no cuenta como decisión. Solo fuentes del sistema: la página no pide nada a otros dominios (quitado Google Fonts de la de S5), y todo el texto entra con `textContent`. Nuevo campo `warnings` en `ReviewItem` (los avisos del paso 4), fuera del hash. Probada en Chrome: elegir Clásicos respeta el máximo, las respuestas sobreviven a recargar y las decisiones que arma la página tienen los mismos hashes que Python y pasan su validación. La interfaz solo está en español porque es una herramienta interna, no una página de la web.
- **Paso 3** (`issue_block.py`, `.github/ISSUE_TEMPLATE/revision.yml`, botón «Enviar» de la página): bloque de texto con una cabecera y una línea JSON por decisión, sin `reviewed_by`, `reviewed_at` ni `source`, que pone el workflow a partir del Issue. GitHub rellena el formulario desde la URL; el límite que manda es el de la redirección al login sin sesión (unos 6950 caracteres), así que la página usa 6000 y reparte en partes; una decisión que no cabe sola se pega a mano. Detalles en [resultados](results/README.md).
- **Puntos abiertos para el paso 4**, salidos del modelo:
  - si Sofía corrige solo el español, ¿se rehace el inglés con el LLM (y pasa las comprobaciones) o se le pide también el inglés? El modelo admite las dos cosas;
  - la nota del grado rata ↔ humano se ve en la web, así que necesita su versión en inglés: el mismo problema.

## Riesgos
- **Longitud de la URL** del Issue: una ficha corregida en ES + EN puede no caber. Plan B: enviar por partes, o adjuntar un archivo al Issue (por comprobar qué tipos acepta GitHub y si el workflow puede leerlo).
- **Sofía no quiere cuenta de GitHub** o la prueba falla: opción D (Sheets) con la WIF de S2.
- **Comentarios ajenos en los Issues:** el workflow los ignora, pero ella los vería.
