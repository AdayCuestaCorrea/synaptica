# Spike S3 · Visor 3D (decisión D3)

Plan aprobado por Aday el 2026-11-11 y cambiado ese mismo día tras el paso 2: la maqueta A (siibra-explorer embebido) queda descartada y la sustituye la **C (Niivue)**. Resultado: el ADR `docs/adr/0003-visor.md`.

Cambiado otra vez el 2026-11-11 tras el paso 6: **Sofía elige C** y pide ajustes ([`results/peticiones-sofia.md`](results/peticiones-sofia.md)), que entran como pasos 7.1–7.9 antes de publicar.

## Objetivo
Dos maquetas del visor con los dos atlas **lado a lado**, Waxholm (rata) y Julich-Brain (humano), publicadas en GitHub Pages y **sin depender de EBRAINS al usarlas**: los datos salen de nuestra web.
- **B:** three.js con mallas propias. Todo lo programamos nosotros: vista 3D de superficies.
- **C:** Niivue con volúmenes propios. Visor de volúmenes ya hecho: cortes 2D y vista 3D.

Primero se descarta lo que no cumpla los requisitos duros de D3. Entre lo que pase, **elige Sofía**. Si solo pasa una tecnología, se le enseñan dos variantes de diseño de esa (por ejemplo, rotación sincronizada o independiente).

Requisitos duros:
- GitHub Pages, sin backend propio;
- regiones clicables por ID;
- licencias compatibles, sin mezclar los atlas;
- peso razonable en móvil;
- los dos atlas a la vez;
- un corte 2D sincronizado con el 3D (añadido tras ver las maquetas), con el 3D como vista principal para no solaparse con The Folded Mind (SCOPE §1).

Además, aprendido de la A: sin ventanas al entrar, sin seguimiento de terceros y sin peticiones a otros dominios en tiempo de uso.

## Regiones de prueba
Sofía propone que el contenido de la Fase 2 empiece por las estructuras de la superficie y luego añada las internas. Para el spike se elige **una de cada tipo**, porque las dos plantean problemas técnicos distintos. IDs confirmados en el paso 1 (`results/README.md`):

| Tipo | Waxholm v4.01 | Julich-Brain v3.1 (etiqueta en el mapa de máxima probabilidad) |
|---|---|---|
| Superficie | M1, 408 | Area 4a, 76 · Area 4p, 142 |
| Interna | HF, 1021 (CA1–3, DG, SUB, FC) | CA1, 146 · CA2, 44 · CA3, 174 · DG, 120 · Subc, 172 |
| Tercera, si cabe en el peso | Am-u, 501 (sin subdividir) | CM, 141 · LB, 75 · SF, 191 · Astr, 5 · VTM, 66 · IF, 149 · MF, 188 |

- La interna sirve para ver cómo se muestra algo tapado por la corteza: transparencia, corte o aislar la región.
- El grado de equivalencia se muestra como «pendiente de Sofía». No se inventa.

## Pasos
0. **Preparación.** *Hecho.* Grupo `spike-s3` (`brainglobe-atlasapi`, `siibra`, `trimesh`); datos en `data/cache/s3/`, sin versionar.
1. **Datos y licencias.** *Hecho* (`results/README.md`, `docs/fuentes.md`).
2. **Maqueta A, siibra-explorer embebido.** *Hecho y descartada* (`results/maqueta-a.md`):
   - no avisa a la página que lo embebe; solo un plugin que el usuario aprueba en cada visita y en cada visor;
   - tres ventanas al entrar y Matomo activado por defecto;
   - 6,8 MB de código antes de los datos;
   - interfaz de escritorio en móvil;
   - dependencia total de EBRAINS.

   El aviso por plugin no se llegó a probar, y no se prueba: aunque funcionara, la confirmación en cada visita ya es mala experiencia.
3. **Datos para B y C.** Un script, `spikes/s3/build_assets.py`, genera lo que sirven las dos maquetas. Salida en `spikes/s3/site/data/`, con un archivo por atlas y su licencia al lado. Nunca se combinan los dos atlas en un archivo.
   - **Para B (mallas):**
     - rata: las mallas de BrainGlobe de las regiones de prueba más el contorno del cerebro;
     - humano: marching cubes sobre el mapa de máxima probabilidad;
     - se simplifican y se comprimen (meshopt o Draco), en **un glTF por atlas**, con el ID de la región en cada nodo.
   - **Para C (volúmenes):**
     - NIfTI de etiquetas por atlas: Waxholm reducido de 39 µm a la resolución que quepa en el presupuesto, midiendo dos o tres;
     - el mapa de máxima probabilidad de Julich-Brain tal cual (1 mm, 405 KB);
     - más una tabla de colores y nombres por atlas.
   - **Fondo opcional:** la RM de plantilla de Waxholm (CC BY-SA 4.0) y la MNI152 2009c (licencia por confirmar), cada una con su licencia. Si no cabe en el peso, se va sin fondo.
   - **Hemisferios en Julich-Brain:** el área izquierda y la derecha llevan la misma etiqueta. Hay que averiguar cómo las distingue siibra (fragmento o coordenada x) y dejar el ID con su lado.
   - **Tabla de equivalencias de prueba**, `spikes/s3/site/data/equivalencias.json`: solo IDs y nombres, con el grado como `"pendiente de Sofía"`. Es dato propio y no lleva geometría.
4. **Maqueta B, three.js.** Versión fija (0.187.0, MIT), guardada en el repositorio.
   - Dos lienzos lado a lado, uno encima del otro en móvil.
   - Al hacer clic, el ID de la región y su panel, y la región equivalente se resalta en el otro atlas.
   - Las estructuras internas, con transparencia de la corteza o aislando la región.
5. **Maqueta C, Niivue.** Versión fija (0.69.0, BSD-2-Clause), guardada en el repositorio, no desde un CDN.
   - Dos lienzos con el mismo comportamiento que la B: clic → ID (el valor del vóxel bajo el cursor), panel y resaltado de la equivalente.
   - Se prueban dos vistas: solo 3D, y 3D más un corte.
6. **Mediciones de B y C**, en `results/maqueta-b.md` y `results/maqueta-c.md`:
   - peso transferido total (código más datos);
   - tiempo hasta poder interactuar, con un móvil y red lenta simulada (Chrome, «Slow 4G» y CPU ×4);
   - fluidez al girar;
   - funcionamiento táctil;
   - comprobación de que no se pide nada a otros dominios.

   Presupuesto inicial: unos **3 MB por atlas** comprimido.
7. **Ajustes que pide Sofía en C** (P1–P7 de `results/peticiones-sofia.md`). Un commit por subpaso.
   1. **Resumen y plan.** El resumen de sus peticiones, este plan y SCOPE. *Hecho.*
   2. **Paleta tranquila (P5).** Colores por grupo de la jerarquía, en tonos suaves e iguales en 2D y 3D, en un campo nuevo de `labels.json`; el color oficial se conserva. *Hecho* (`results/maqueta-c.md`, paso 7.2).
   3. **Recorte sagital y sincronía (P1, P2).** Recorte 3D sagital y corte 2D coronal. Dos variantes, elegibles con `?sync=punto|deslizadores`: un punto común (línea arrastrable en el 2D y plano fino en el 3D) o dos deslizadores.
   4. **Clic sincronizado y nombre (P3, P6).** Centroides por región, un archivo por atlas; el otro visor selecciona la pieza, gira hacia ella y lleva su corte hasta ella; aviso «sin pareja todavía»; nombre completo y sigla visibles, con la sigla marcada para el glosario de la Fase 2.
   5. **Coordenadas (P7).** Bregma y Lambda en Waxholm, solo de una publicación citada; ejes en mm. El humano, en mm MNI. Si no hay fuente, se para y se avisa.
   6. **Modos de vista y atlas en blanco y negro (P4).** Selector «Color · Atlas · Tinción», uno a la vez; grises y contornos en 2D y en 3D. Los archivos extra se cargan solo al elegir el modo.
   7. **Tinción dibujada (P4).** Aspecto de tinción generado desde las etiquetas, con el aviso «ilustración, no es una tinción real» en el lienzo.
   8. **Tinción real (P4).** Búsqueda de histologías alineadas a Waxholm y a MNI, con licencia y peso (`results/tincion.md`). Se integran solo si hay datos válidos que quepan; si no, al backlog.
   9. **Móvil.** Resolución del 3D limitada en móviles, nuevas mediciones y prueba en un móvil real.
   10. **Publicación.**
       - En GitHub Pages, en `/synaptica/spikes/s3/`. **Se confirma con Aday antes de tocar Pages.**
       - Además, como artifact de claude.ai para que Sofía lo vea cómodamente.
       - Página de respuestas al estilo de S5, que sirve también como prueba de D5: variante de sincronía, tinción dibujada o real, paleta y notas.
8. **ADR `0003-visor.md`.** Cifras de A, B y C (antes y después de los ajustes), licencias, la elección de Sofía, lo que elija en 7.10 y la casilla de SCOPE.

## Licencias
- Los datos derivados heredan la licencia de su atlas:
  - Waxholm: CC BY 4.0, para las delineaciones y todo lo que sale de ellas (mallas, volúmenes de etiquetas); la RM de plantilla es CC BY-SA 4.0;
  - Julich-Brain: CC BY-NC-SA 4.0.
- Van en archivos separados y nunca se combinan. Verlas lado a lado no las mezcla.
- Cada maqueta muestra la licencia y la cita de cada atlas junto a su lienzo.
- Las librerías (three.js, MIT; Niivue, BSD-2-Clause) se guardan con su archivo de licencia.
- La tabla de equivalencias es dato propio (de Sofía): IDs y nombres de región, sin geometría.
