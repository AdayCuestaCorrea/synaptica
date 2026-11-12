# D3: Visor 3D de Neuro Atlas

- **Estado:** propuesta (2026-11-12, Fase 0, spike S3). Sofía eligió la maqueta C (Niivue) el 2026-11-11. Falta su revisión de los ajustes, esta tarde, y que Aday la acepte; hasta entonces D3 sigue en «Abiertas».
- **Relacionadas:** [SCOPE §8 D3](../../SCOPE.md#8-decisiones) · [plan de S3](../../spikes/s3/PLAN.md) · [resultados](../../spikes/s3/results/) · [fuentes](../fuentes.md) (atlas y BigBrain) · D5 (revisión de Sofía, para el grado de las parejas)

## Contexto
Neuro Atlas enseña el cerebro de la rata y el del humano **lado a lado**: al elegir una región en uno, el otro marca su equivalente (SCOPE §1). El visor tiene que cumplir:
- funcionar en **GitHub Pages**, sin backend propio, a 0 €;
- **regiones clicables por ID**, para enlazar con el glosario y con las fichas;
- **licencias compatibles**: Waxholm (CC BY 4.0) y Julich-Brain (CC BY-NC-SA 4.0) nunca se combinan en un mismo dato derivado;
- **un peso razonable en móvil**: presupuesto inicial de unos 3 MB por atlas, comprimidos;
- **los dos atlas a la vez**;
- tras ver las maquetas, también un **corte 2D sincronizado con el 3D**, con el 3D como vista principal.

Requisito añadido en el plan: en tiempo de uso, sin ventanas, sin seguimiento y sin pedir nada a otros dominios.

## Qué midió S3
Se probaron tres maquetas. Todas se midieron igual (`spikes/s3/measure.mjs`):
- un móvil simulado de 390 × 844 con DPR 3 y táctil;
- la red «Slow 4G» de DevTools y la CPU ×4;
- texto con gzip, como en Pages.

La fluidez es con WebGL **por software**, así que es una cota pesimista.

| | A · siibra-explorer embebido | B · three.js con mallas propias | C · Niivue con volúmenes propios |
|---|---|---|---|
| Regiones clicables por ID | Solo con un plugin que se aprueba **en cada visita** y en cada visor | Sí, pero solo las que tienen malla (las de prueba) | **Sí, todo el atlas**, sin generar nada por región |
| Peso | 6,8 MB solo de código, antes de los datos | **1,07 MB** | 1,91 MB (Niivue: 0,80 MB) |
| Hasta poder usarla | — | **10 s** | 16 s |
| Fluidez al girar | — | 20 fps | 3 fps a DPR 3; 22 fps a DPR 1 |
| Otros dominios | EBRAINS (código, datos y términos) y Matomo **activado por defecto** | Ninguno | Ninguno |
| Ventanas al entrar | Tres por visor | Ninguna | Ninguna |
| Corte 2D | Sí (neuroglancer) | No | **Sí, de serie** |

- **A** quedó descartada en el paso 2 ([resultados](../../spikes/s3/results/maqueta-a.md)): depende entera de EBRAINS, trae seguimiento y no deja clicar regiones sin pedir permiso.
- **B** cumplía los requisitos duros ([resultados](../../spikes/s3/results/maqueta-b.md)), y Aday la borró el 2026-11-11 al ver que no se iba a usar. Sus cifras se quedan para este ADR.
- **Sofía eligió C** ([peticiones](../../spikes/s3/results/peticiones-sofia.md)) y pidió ajustes. Se hicieron todos sobre C (pasos 7.1–7.10, [resultados](../../spikes/s3/results/maqueta-c.md)):
  - paleta tranquila por familias;
  - corte 2D coronal y recorte 3D sagital, sincronizados;
  - clic sincronizado: el otro cerebro gira y lleva su corte a la pareja;
  - mm desde Bregma en la rata y MNI en el humano;
  - tres modos: color, atlas en blanco y negro con contornos, y tinción;
  - la tinción, dibujada o real (BigBrain en el humano);
  - y dos mejoras de Aday: buscador de áreas y área bajo el punto de los tres ejes.

**C después de los ajustes**, publicada en Pages y medida allí ([7.10](../../spikes/s3/results/maqueta-c.md#paso-710-publicación-en-github-pages-2026-11-12)):

| Medida | Resultado |
|---|---|
| Peso | 1,96 MB, igual que antes de los ajustes (+0,05 MB) |
| Hasta poder usarla | unos 16 s |
| Fluidez al girar | 9–10 fps con el 3D limitado a DPR 1,5 en pantallas táctiles |
| Modo atlas | 0 bytes más; los contornos se calculan en el navegador (0,2–0,5 s en el móvil simulado) |
| Tinción real | +1,62 MB, solo si se pide; el humano suma 2,3 MB, dentro del presupuesto |

En un móvil real (Samsung Galaxy S23 Ultra, con Chrome y Brave) funciona. Al tocar una región todavía tarda un poco en responder: apuntado para la Fase 2.

## Decisión
**Niivue con volúmenes de etiquetas propios**, uno por atlas:
- un NIfTI de etiquetas por atlas, más sus tablas de nombres (`labels.json`) y coordenadas, generados por un script desde los datos originales;
- cada atlas en su carpeta, con su `licence.json`;
- Niivue 0.69.0 se guarda en el repositorio (BSD-2-Clause, minificado, con las licencias de lo que empaqueta) y se sirve desde nuestra web, sin CDN;
- la lógica propia (selección, parejas, modos, cortes, buscador) va en JavaScript sin framework, como el resto de la web.

En la Fase 1, el script de S3 (`spikes/s3/build_assets.py`) pasa a `src/synaptica/atlas/` con tests, y el visor a `site/static/`. El código del spike no se publica tal cual: se reescribe a partir de él.

## Alternativas consideradas
- **siibra-explorer embebido (A):**
  - clicar una región exige un plugin que se aprueba en cada visita;
  - trae seguimiento de terceros activado por defecto;
  - depende por completo de EBRAINS;
  - pesa 6,8 MB antes de los datos.

  Autohospedarlo exigiría un servidor Python (siibra-api) y mantener un fork de Angular.
- **three.js con mallas propias (B):** era más ligera (1,07 MB y 10 s) y más fluida, pero:
  - cada región clicable necesita su malla, así que para todo el atlas habría que generar y pesar cientos de mallas;
  - no tiene corte 2D, que Sofía pidió;
  - la elección es de Sofía, y eligió C sin querer conservar nada de B.
- **Otro visor (por ejemplo, BrainBrowser o neuroglancer solo):** no se probó. Neuroglancer es el motor de A y arrastra su peso; los demás no aportaban nada que Niivue no tenga para volúmenes de etiquetas.

## Consecuencias
- **A favor:**
  - **todo el atlas es clicable** sin generar nada por región: añadir regiones al contenido no cuesta peso;
  - el corte 2D, los modos y la tinción salen de los mismos datos;
  - sin backend, sin otros dominios y sin seguimiento;
  - es un visor de neuroimagen mantenido, pensado para NIfTI.
- **En contra, y cómo se mitiga:**
  - **Pesa casi el doble que B y tarda unos 6 s más** en red lenta, sobre todo por Niivue (0,80 MB). Está dentro del presupuesto. Si hiciera falta, la Fase 2 puede cargar el visor después del texto de la página.
  - **El 3D por trazado de rayos es caro en pantallas densas.** Se limita a DPR 1,5 en pantallas táctiles (paso 7.9). El toque aún tarda un poco: se mide en la Fase 2.
  - **Dependemos de comportamientos internos de Niivue 0.69** que pueden cambiar entre versiones:
    - en 3D, solo lee el vóxel con doble clic, así que un clic corto le manda uno;
    - sube los valores bajos de la tabla de colores (su incidencia 1139), por eso se usa un desplazamiento de 16;
    - con el dedo, usaba la posición del gesto anterior.

    Se fija la versión, cada parche está comentado en el código, y subir de versión exige repetir las pruebas táctiles de S3.
  - **Licencias:** el NIfTI de Julich-Brain y BigBrain es NC-SA y va en su propia carpeta, con su licencia junto al lienzo. SYNAPTICA ya acepta NC (CLAUDE.md).
  - **Tinción de la rata:** no hay histología 3D con licencia alineada a Waxholm. Está en el backlog (SCOPE §10); mientras tanto, la tinción dibujada lleva el aviso en el propio lienzo.

## Pruebas
- **Plan:** [`spikes/s3/PLAN.md`](../../spikes/s3/PLAN.md).
- **Resultados por maqueta:** [A](../../spikes/s3/results/maqueta-a.md) · [B](../../spikes/s3/results/maqueta-b.md) · [C, pasos 5–7.10](../../spikes/s3/results/maqueta-c.md).
- **Datos y licencias:** [`results/README.md`](../../spikes/s3/results/README.md) · [tinción](../../spikes/s3/results/tincion.md).
- **Mediciones:** `spikes/s3/results/measure-*.json`. La última, contra Pages: `measure-c-pages.json`.
- **Peticiones de Sofía:** [`peticiones-sofia.md`](../../spikes/s3/results/peticiones-sofia.md). **Notas de UX** para la Fase 2: [`notas-ux.md`](../../spikes/s3/results/notas-ux.md).
- **Maqueta publicada:** https://adaycuestacorrea.github.io/synaptica/spikes/s3/c/ (workflow `.github/workflows/pages.yml`).
- **Tests sin red:** `uv run pytest spikes/s3/tests` (datos y licencias de `build_assets.py`).
