# S3 · Paso 1: datos y licencias de los atlas

Medido el 2026-11-11 con `spikes/s3/atlases.py` (cifras completas en `waxholm.json` y `julich.json`, un archivo por atlas: no se mezclan). Descargas en `data/cache/s3/` (322 MB, sin versionar).

## Waxholm (rata), vía BrainGlobe `whs_sd_rat_39um`

- **Versión: v4.01**, no v4. BrainGlobe solo dice «versión 3.0» (es la de su empaquetado) y cita Kleven et al. 2023, pero trae las tres regiones que, según el KG, añadió v4.01 (msp5t, 5n, AOA-u). siibra solo tiene hasta v4.
- **Regiones:** 314 estructuras en el árbol, 224 hojas (las 224 que anuncia v4.01).
- **IDs:** enteros; en BrainGlobe el ID es el mismo valor que lleva el vóxel en el volumen de anotación (M1 = 408).
- **Licencia:** los metadatos de BrainGlobe **no traen licencia**. Las tres fuentes consultadas dicen **CC BY 4.0** para las delineaciones:
  - EBRAINS KG, v4 (`fadcd2cb-9e8b-4e01-9777-f4d4df8f1ebc`) y v4.01 (`2cf40e61-fae1-4ab3-b7de-cb8fdfa19b70`);
  - la página del proyecto en NITRC: «The atlas is shared under the CC BY 4.0 licence».
  - La **imagen de RM de plantilla** es otro conjunto de datos (DOI 10.25493/DTSG-ZBS) y es **CC BY-SA 4.0** según DataCite. Las mallas por región salen de las delineaciones, no de la plantilla.
- **Mallas:** 314 mallas (629 archivos con sus manifiestos) en formato *neuroglancer precomputed* sin comprimir: **16,8 MB** en total. El contorno del cerebro (ID 1000), 824 KB. Se pesan desde el listado del bucket, sin descargarlas.

## Julich-Brain (humano), vía siibra 1.0.1a27

- **Versión: v3.1**, la más reciente en siibra (también están v1.18, v2.9 y v3.0.3).
- **Licencia:** **CC BY-NC-SA 4.0** según el KG (`f1fe19e8-99bd-44bc-9616-a52850680777`) y DataCite (DOI 10.25493/KNSN-XB4).
- **Regiones:** 454 hojas en el árbol; 414 están en el mapa de máxima probabilidad (MPM). Algunas áreas solo están mapeadas como conjunto (por ejemplo, «CM (Amygdala)» entero, no sus 3 subnúcleos).
- **IDs:** el ID de siibra es una cadena (`JULICH_BRAIN_CYTOARCHITECTONIC_ATLAS_V3_1_AREA_4A_PRECG`); en el MPM, cada área tiene una etiqueta entera, la misma en los dos hemisferios, que se distinguen por el volumen.
- **MPM:** sí, en MNI152 2009c no lineal asimétrico: 193 × 229 × 193 vóxeles de 1 mm, `uint8`, 405 KB en NIfTI comprimido.
- **Mallas:** no hay mallas por región en volumen; hay que generarlas (marching cubes sobre el MPM). Sí hay un mapa de superficie etiquetado en fsaverage, que sirve para las áreas de corteza pero no para el hipocampo ni la amígdala.

## Regiones de prueba

El grado de equivalencia queda **pendiente de Sofía**: aquí solo se dice qué existe en cada atlas.

| Tipo | Waxholm v4.01 (ID · sigla) | Malla | Julich-Brain v3.1 (etiqueta MPM) |
|---|---|---|---|
| Superficie | 408 · M1 «Primary motor area» | 47 KB | Area 4a (PreCG), 76 · Area 4p (PreCG), 142 |
| Interna | 1021 · HF «Hippocampal formation» (incluye FC, SUB, CA1–3, DG) | 96 KB | CA1, 146 · CA2, 44 · CA3, 174 · DG, 120 · Subc (complejo subicular), 172 |
| Tercera | 501 · Am-u «Amygdaloid area, unspecified» | 63 KB | CM, 141 · LB, 75 · SF, 191 · Astr, 5 · VTM, 66 · IF, 149 · MF, 188 |

- La corteza motora primaria existe en los dos, pero Julich-Brain la divide en dos áreas (4a y 4p).
- En Waxholm, la amígdala es **una sola región sin subdividir**; en Julich-Brain son 7 núcleos.
- Los tamaños de malla son sin comprimir; la compresión y el presupuesto por atlas se miden en el paso 3.

## Peticiones

User-Agent genérico (`synaptica-spike/0.1`), sin contacto, en serie y con 1 s de pausa: listado del bucket de BrainGlobe, configuración y mapas de siibra, DataCite, el buscador público del KG (sin token) y una visita a NITRC. La descarga del atlas que hace BrainGlobe por dentro va por S3 anónimo con el User-Agent por defecto de botocore, que no lleva datos personales.
