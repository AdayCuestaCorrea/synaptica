# Spike S3 · Visor 3D (decisión D3)

Plan aprobado por Aday el 2026-11-11. Resultado: el ADR `docs/adr/0003-visor.md`.

## Objetivo
Dos maquetas del visor con los dos atlas **lado a lado**, Waxholm (rata) y Julich-Brain (humano), publicadas en GitHub Pages:
- **A:** siibra-explorer embebido;
- **B:** three.js con mallas propias.

Primero se descarta lo que no cumpla los requisitos duros de D3. Entre lo que pase, **elige Sofía**. Si solo pasa una tecnología, se le enseñan dos variantes de diseño de esa (por ejemplo, rotación sincronizada o independiente).

Requisitos duros:
- GitHub Pages, sin backend propio;
- regiones clicables por ID;
- licencias compatibles, sin mezclar los atlas;
- peso razonable en móvil;
- los dos atlas a la vez.

## Regiones de prueba
Sofía propone que el contenido de la Fase 2 empiece por las estructuras de la superficie y luego añada las internas. Para el spike se elige **una de cada tipo**, porque las dos plantean problemas técnicos distintos:
- **Superficie:** una región de corteza que exista en los dos atlas, probablemente la corteza motora primaria. Se confirma en el paso 1.
  - Julich-Brain no tiene lóbulos: tiene áreas citoarquitectónicas que habría que agrupar.
  - La rata, que es lisencéfala, tampoco tiene lóbulos como los humanos.
- **Interna:** el hipocampo, que es la equivalencia más clara. Sirve para ver cómo se muestra algo tapado por la corteza: transparencia, corte o aislar la región.
- Una tercera, la amígdala, si el presupuesto de peso lo permite.

El grado de equivalencia se muestra como «pendiente de Sofía». No se inventa.

## Pasos
0. **Preparación.**
   - Grupo `spike-s3`:
     - `brainglobe-atlasapi`: Waxholm con mallas por región;
     - `siibra`: los mapas de Julich-Brain;
     - `trimesh`: convertir volúmenes en mallas y simplificarlas.
   - Los datos van a `data/cache/s3/`, sin versionar.
   - three.js con una versión fija, guardado en el repositorio.
1. **Datos y licencias.**
   - Waxholm: versión (v4), número de regiones, IDs, licencia de los metadatos y peso de las mallas.
   - Julich-Brain: versión, licencia en el EBRAINS Knowledge Graph y mapa de máxima probabilidad.
   - Qué regiones de prueba existen en los dos atlas.
   - Se completa la línea «Atlas» de `docs/fuentes.md`, que es lo que queda de S1.
2. **Maqueta A.**
   - Dos iframes de atlases.ebrains.eu.
   - Qué se mide:
     - si se puede abrir con una región seleccionada desde la URL;
     - si avisa a la página al hacer clic (postMessage o plugin);
     - peso y fluidez en móvil;
     - dependencia de EBRAINS y de sus términos.
   - Autohospedarlo exige `siibra-api`: solo se verifica.
3. **Maqueta B.**
   - Un script genera las mallas:
     - rata: las de BrainGlobe;
     - humano: marching cubes sobre el mapa de máxima probabilidad;
     - se simplifican y se comprimen (meshopt o Draco), en **un glTF por atlas** con el ID de la región en cada nodo.
   - Dos lienzos lado a lado, uno encima del otro en móvil.
   - Al hacer clic, el ID de la región y su panel. La región equivalente se resalta a partir de una tabla de prueba.
   - Presupuesto inicial: unos 3 MB por atlas comprimido, medido con un móvil y red lenta simulada.
4. **Publicación.**
   - En GitHub Pages, en `/synaptica/spikes/s3/`; se confirma con Aday antes de tocar Pages.
   - Además, como artifact de claude.ai para que Sofía lo vea cómodamente.
   - Página de respuestas al estilo de S5, que sirve también como prueba de D5.
5. **ADR `0003-visor.md`.** Cifras, licencias, la elección de Sofía y la casilla de SCOPE.

## Licencias
- Las mallas derivadas heredan la licencia de su atlas: Waxholm, CC BY 4.0 (salen de las delineaciones; la RM de plantilla es CC BY-SA 4.0 y no se usa para las mallas), y Julich-Brain, CC BY-NC-SA 4.0. Corregido el 2026-11-11 tras el paso 1.
- Van en archivos separados y nunca se combinan. Verlas lado a lado no las mezcla.
- La tabla de equivalencias es dato propio (de Sofía): IDs y nombres de región, sin geometría.
