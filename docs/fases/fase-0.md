# Fase 0 — Cimientos

> **Cerrada** el 2026-11-13 por Aday, con el visto bueno de Sofía. Todas las decisiones que exigía el cierre (D1, D3, D4 y D5) tienen su ADR aceptado.

## Para qué servía esta fase
Antes de escribir el motor de la web hacía falta responder a cinco preguntas. Sus respuestas cambian el diseño, y equivocarse sale caro una vez construido:

| Pregunta | Spike | Decisión |
|---|---|---|
| ¿De dónde salen los datos, con qué límites y con qué licencia? | S1 Fuentes | `docs/fuentes.md` |
| ¿Dónde vive el almacén, si tiene que costar 0 €? | S2 Almacén | D1 |
| ¿Qué visor 3D cumple con Pages, móvil y licencias? | S3 Visor | D3 |
| ¿Cómo revisa Sofía sin terminal ni git? | S4 Revisión | D5 |
| ¿Qué modelos de lenguaje escriben y cuáles juzgan? | S5 LLM | D4 |

Un **spike** es un experimento corto y desechable para medir algo antes de decidir. Su código no pasa tal cual a la web: lo que pasa es la decisión y las cifras que la sostienen. Por eso cada spike vive en `spikes/sN/`, con sus propias dependencias (`--group spike-sN`) que la CI normal no instala.

Además se montó el andamiaje del repositorio:
- `pyproject.toml` con uv, Python 3.14, ruff y pytest;
- la CLI `syn` con `--version` y `doctor`;
- la CI sin red;
- licencias (AGPL-3.0 para el código y CC BY-SA 4.0 para los textos), README en los dos idiomas, e índices de ADR y de fases.

## Lo que se decidió y por qué

### S1 · Fuentes → `docs/fuentes.md`
- Se midieron 15 fuentes con una petición real cada una: límites, clave, licencia y volumen.
- Las respuestas se guardaron como fixtures en `tests/fixtures/`, sin texto de editores, para que los tests no usen la red.
- **Lo importante:**
  - los RSS públicos de Nature, Science y Cell funcionan (7 revistas, todas con DOI), así que el riesgo de no tener canal desapareció;
  - Crossref trae las retractaciones de Retraction Watch;
  - bioRxiv es lenta (unos 13 s por petición) y su volumen de una semana crece días después, así que hay que volver a consultar hacia atrás y deduplicar por DOI.

### S2 · Almacén → [D1](../adr/0001-almacen.md): DuckDB, con espejo semanal en BigQuery
- BigQuery sandbox funciona desde GitHub Actions sin tarjeta ni clave guardada, con Workload Identity Federation.
- **Pero tiene 10 GiB de almacenamiento de por vida, que no se recuperan al borrar.** Es incompatible con reconstruir el almacén cada día, que es el patrón de Paleo Atlas.
- Por eso el almacén de trabajo es DuckDB, como en Paleo, y una vez por semana se suben solo los marts publicados a BigQuery.

### S5 · LLM → [D4](../adr/0004-llm.md): carga inicial en local y después Groq con juez de otra familia
- **Groq gratis:** 1000 peticiones al día y 8000 tokens por minuto por modelo, medidos. Ya no hay Llama.
- **El modelo local de Aday:** 122 tokens/s.
- **La cadena de Paleo con 10 artículos de PubMed:** 8–9 de cada 10 resúmenes publicables. El juez de otra familia cazó 3 errores reales que las comprobaciones mecánicas dejaban pasar.
- **Revisión ciega de Sofía:** los dos Qwen empatan, y el español es el punto débil de ambos. El juez coincidió con ella en 17 de 19 casos (kappa ≈ 0,60). Los prompts pasaron a v2 con lo que pidió; volver a ejecutarlos queda para la Fase 1.

### S3 · Visor 3D → [D3](../adr/0003-visor.md): Niivue con volúmenes de etiquetas propios
- **Se probaron tres maquetas:**
  - A, siibra-explorer embebido: descartada por su plugin con permiso en cada visita, por el seguimiento de terceros y por pesar 6,8 MB solo de código;
  - B, three.js con mallas: 1,07 MB, pero solo se podían clicar las regiones con malla;
  - C, Niivue con volúmenes: 1,91 MB y todo el atlas clicable.
- **Sofía eligió C** y pidió ajustes, que se hicieron en los pasos 7.1–7.10:
  - corte 2D y recorte 3D sincronizados;
  - clic que lleva al otro cerebro;
  - mm desde Bregma;
  - modos color, atlas y tinción (con BigBrain real en el humano);
  - buscador de áreas.
- **Publicada en Pages:** 1,96 MB, unos 16 s en un móvil con red lenta, sin otros dominios, y probada en un móvil real.
- **La revisión de Sofía (2026-11-12) pidió tres cosas:**
  - **Conservar la tinción dibujada y la real.**
  - **Completar el cerebro humano.** Le faltaban el cerebelo, el tronco y la médula, porque Julich-Brain es citoarquitectónico. Una auditoría por familias de regiones encontró además huecos en el estriado, los ventrículos, el hipotálamo y la sustancia blanca. Se rellenaron con tres capas más, cada una solo donde las anteriores no tienen nada: CerebrA, CIT168 y el mapa de sustancia blanca de ICBM 2009c. Sigue siendo un solo cerebro en pantalla.
  - **Una tinción real para la rata.** No existe en 3D con licencia, así que el corte 2D muestra el Nissl real registrado más cercano (Blixhavn et al. 2023).
- **Quedan sin atlas utilizable**, en el backlog: la médula, el tronco dividido, el bulbo olfatorio y los tractos.
- **Peso final:** unos 2,5 MB y 19 s en un móvil simulado con red lenta, sin otros dominios. Sofía da el visto bueno y Aday acepta el ADR el 2026-11-13.

### S4 · Revisión → [D5](../adr/0005-revision.md): página de revisión generada que envía un Issue de GitHub
- **El prototipo:**
  - una página estática generada desde la cola de revisión;
  - Sofía decide y pulsa «Enviar», y GitHub abre el formulario de Issue ya relleno;
  - un script lee los Issues de su cuenta, comprueba el esquema y el hash de lo que vio, y vuelve a pasar las comprobaciones mecánicas a sus correcciones.
- Probado de punta a punta con un Issue real (el #1). Tiene 111 tests sin red.
- **Prueba con Sofía (2026-11-12):** tres rondas reales con su cuenta (Issues #2–#10), sin terminal ni git.
  - Cumple los criterios salvo el tiempo de la primera ronda: 38 min, aunque hizo bastante más de lo pedido.
  - Prefiere esto a una hoja de cálculo y no le importa que sus decisiones sean públicas.
  - La prueba destapó 6 fallos nuestros, ya corregidos con test.
  - Aday cerró D5 con la opción C (ADR 0005). Sus correcciones también pasan las comprobaciones mecánicas (CLAUDE.md).

### Decisiones sin spike
Cerradas por Aday en la Fase 0:
- **D8 (licencias):** AGPL-3.0 y CC BY-SA 4.0.
- **D9:** repositorio público; Sofía no es colaboradora.

D2, D6 y D7 siguen con la recomendación de `SCOPE.md` §8:
- **D2:** copiar y adaptar código de Paleo;
- **D6:** procesamiento a escala solo si el volumen lo justifica;
- **D7:** empezar en `adaycuestacorrea.github.io/synaptica`.

## Conceptos, desde cero
- **ADR:** una página por decisión: contexto, decisión, alternativas, consecuencias y pruebas. Sirve para explicar el porqué dentro de un año sin depender de la memoria.
- **Fixture:** una respuesta real de una API guardada en el repositorio. Los tests la leen en vez de llamar a la red, así que son rápidos, reproducibles y no gastan cupo.
- **Workload Identity Federation:** GitHub Actions demuestra a Google quién es con un token firmado de cada ejecución, en vez de con una clave guardada. No hay secreto que pueda filtrarse.
- **Volumen de etiquetas (NIfTI):** una rejilla 3D donde cada vóxel guarda el número de la región a la que pertenece. Clicar es leer el número bajo el puntero, y por eso todo el atlas es clicable sin generar una malla por región.
- **Juez de otra familia:** un segundo modelo, entrenado por otra empresa, revisa lo que escribió el primero. Así no comparten los mismos sesgos.
- **Licencias que no se mezclan:** Waxholm (CC BY 4.0), Julich-Brain (CC BY-NC-SA 4.0) y las capas humanas añadidas se sirven en archivos separados y solo se superponen en pantalla. Un dato que combinara dos heredaría la licencia más restrictiva.
- **Corte registrado:** una sección histológica real que alguien colocó a mano en el atlas, primero con un ajuste afín (QuickNII) y después con una deformación por triángulos (VisuAlign). Con ese registro se puede pintar el corte en el plano del visor sin montar un volumen 3D.

## Cómo se comprueba
- `uv run pytest` y `uv run ruff check .` en la CI, sin red. Cada spike tiene sus tests aparte:
  - `uv run --group spike-s3 pytest spikes/s3/tests`;
  - `uv run --group spike-s4 pytest spikes/s4/tests`.
- **Mediciones reproducibles:**
  - S2, con su workflow (`spike-s2.yml`);
  - S3, con `spikes/s3/measure.mjs`: móvil simulado, «Slow 4G» y CPU ×4. Las cifras están en `spikes/s3/results/measure-*.json`. Además, `spikes/s3/coverage.py` compara qué tiene cada cerebro por familias;
  - S5, con los JSON de `spikes/s5/results/`.
- **La maqueta publicada:** https://adaycuestacorrea.github.io/synaptica/spikes/s3/c/
- **Sofía revisó lo que le toca sin terminal ni git:** los resúmenes de S5, la maqueta de S3 (elección y ajustes) y el flujo de S4, con tres rondas reales.

## Qué salió mal (y qué se aprendió)
- **BigQuery** parecía la opción natural para el CV. El cupo de por vida solo apareció al medirlo, y cambió D1. *Lección:* medir antes de decidir; para eso están los spikes.
- **La licencia de Waxholm** figuraba como CC BY-SA. Al comprobarla en el EBRAINS KG resultó ser CC BY 4.0 (la de la RM de plantilla sí es BY-SA). Se corrigió en todos los documentos.
- **siibra-explorer** se dejaba embeber, pero no avisa a la página que lo contiene, y trae Matomo activado antes de que el usuario acepte nada. *Lección:* que un visor se deje embeber no basta; hay que medir qué hace en tiempo de uso.
- **Niivue 0.69** tiene comportamientos internos que hubo que sortear:
  - en 3D solo lee el vóxel con doble clic;
  - con tablas de colores grandes pintaba el fondo opaco;
  - en el móvil usaba la posición del gesto anterior, que giraba el cerebro boca abajo y perdía toques.

  Solo apareció en un móvil real: el simulador mandaba los eventos demasiado ordenados.
- **La maqueta B** se mantuvo hasta el paso 7.5 aunque Sofía ya había elegido C. Aday la borró porque confundía.
- **Un atlas solo enseña lo que etiqueta.** El cerebro humano no tenía cerebelo ni tronco porque Julich-Brain no los delimita, y nadie lo vio hasta que Sofía lo comparó con la rata. *Lección:* auditar la cobertura por familias frente al otro atlas, no solo mirar si las regiones de prueba existen.
- **GitHub** falla al rellenar un Issue desde una URL de más de unos 6950 caracteres sin sesión iniciada. La página reparte las decisiones en varios Issues de 6000 como máximo.
- **El ensayo en seco de S4** encontró que una corrección corta y legítima de Sofía se retenía como «frase nueva sin fuente». Ahora sus frases se alinean con las originales.
- **Brave en el móvil** no abre direcciones de la red local. La prueba en un móvil real se hizo con Chrome hasta publicar en Pages.

## Cómo defenderlo en una entrevista
- «Antes de construir, hice cinco spikes con criterios escritos de antemano. Uno cambió la decisión que parecía obvia: BigQuery como almacén, por un cupo de por vida que solo vi al medirlo.»
- «El visor lo eligió la persona que va a usar el contenido. Mi trabajo fue medir las tres opciones con el mismo método (peso, tiempo y fluidez en un móvil con red lenta) y dejar las cifras en un ADR.»
- «Los tests nunca tocan la red: cada fuente tiene fixtures reales. La CI es gratis y reproducible.»
- «Las licencias son un requisito de diseño, no un pie de página. Dos atlas con licencias distintas nunca se combinan en un mismo dato derivado, y la web enseña la licencia de cada uno junto a su lienzo.»
- «El contenido de salud tiene dos barreras: comprobaciones mecánicas y un juez de otra familia de modelos. Medí cuánto coincide el juez con una revisora humana (kappa ≈ 0,60) en vez de suponerlo.»

## Lo que pasa a la Fase 1
- Pasar el script de datos del visor (`spikes/s3/build_assets.py`) a `src/synaptica/atlas/` con tests, y reescribir el visor en `site/static/` (ADR D3).
- El espejo semanal de los marts en BigQuery (D1).
- Volver a ejecutar S5 con los prompts v2 (D4).
- El flujo de revisión de Sofía según el ADR de D5: activar el workflow de recepción (con permiso de Aday), pasar el código al paquete y aplicar las frases que sugiera en la nota.
- Para la Fase 2, de las [notas de UX](../../spikes/s3/results/notas-ux.md): el estudio de UX y UI de Neuro Atlas antes de construirlo.
