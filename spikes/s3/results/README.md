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

# S3 · Paso 3: datos para las maquetas B y C

Generados el 2026-11-11 con `spikes/s3/build_assets.py` (cifras en `spikes/s3/site/data/manifest.json`). Descargó solo lo que faltaba en la caché: el volumen de anotación de Waxholm (4,4 MB), el de hemisferios (0,6 MB) y 4 mallas de BrainGlobe. Una ejecución tarda unos 20 s y es idempotente: dos ejecuciones dan archivos idénticos.

## Qué hay en `site/data/`

Una carpeta por atlas; ningún archivo combina los dos.

| Archivo | Waxholm | Julich-Brain | Para |
|---|---|---|---|
| `<atlas>.glb` | 168 KB · contorno + M1, HF y Am-u, cada una por lado | 181 KB · contorno + 14 áreas, cada una por lado | B |
| `labels.nii.gz` | 536 KB · 171 × 342 × 171 a 117 µm | 539 KB · 193 × 229 × 193 a 1 mm | C |
| `labels.json` | 113 KB · 447 regiones con lado + árbol | 104 KB · 414 áreas con lado | B y C |
| `licence.json` | CC BY 4.0, cita Kleven et al. 2023 | CC BY-NC-SA 4.0, cita del conjunto de datos (DOI 10.25493/KNSN-XB4) | B y C |

Más `equivalencias.json` (3 KB): los tres pares de prueba, con solo IDs y nombres, todos con el grado `"pendiente de Sofía"`.

- **Total por atlas: unos 0,8 MB**, muy por debajo de los 3 MB del presupuesto. Cada maqueta usa solo una parte: B, el glTF y las tablas (unos 270 KB); C, el NIfTI y las tablas (unos 650 KB).
- **Valores:** el valor de cada vóxel y el de cada nodo del glTF es un índice compacto (1…N) que apunta a una fila de `labels.json`, con el ID del atlas y su lado (`L` o `R`).
- **Coordenadas:** milímetros RAS centrados en el cerebro, iguales en los dos atlas para que se vean con la misma orientación.
- **Mallas (B):** decimación cuádrica (12.000 caras por región, 40.000 el contorno) y compresión Draco, con la posición cuantizada a 12 bits. El nodo lleva en `extras` el ID, el lado y el nombre.
  - Rata: las mallas de BrainGlobe, cortadas por lado cara a cara según el volumen de hemisferios. Separarlas en piezas conexas no sirve: HF es una sola pieza que cruza la línea media por las comisuras.
  - Humano: marching cubes sobre el volumen de cada área y lado, suavizado.
  - Las caras se orientan hacia fuera antes de simplificar o cortar, mientras la malla aún está cerrada. El paso de los ejes de BrainGlobe a RAS incluye una reflexión que las daba la vuelta, y three.js no dibuja ni detecta las caras traseras.

## Hemisferios

- **Julich-Brain:** siibra no lo distingue por la coordenada x. El mapa de máxima probabilidad son **dos archivos**, uno por hemisferio (`JulichBrainAtlas_3.1_207areas_MPM_lh_MNI152.nii.gz` y `…_rh_…`), y cada `MapIndex` lleva `fragment = "left hemisphere"` o `"right hemisphere"`; la región de cada lado tiene su propio ID (`…_AREA_4A_PRECG_LEFT`). Los dos archivos no se solapan, pero sus rangos de x se cruzan cerca de la línea media (vóxeles 95–97), así que el lado lo da el archivo.
- **Asimetrías del propio MPM:** algunas áreas tienen tamaños muy distintos en cada hemisferio, y así vienen ya en los archivos de siibra; no es efecto de nuestro proceso. Por ejemplo, el área 4a tiene 2.872 vóxeles a la izquierda y 9.280 a la derecha, y el área 3b, 7.596 y 2.249. 16 etiquetas difieren más de 2,5 veces. Conviene que Sofía lo sepa al ver la maqueta. Cada fila de `labels.json` lleva `label` (la etiqueta del MPM, igual a los dos lados), `side`, `id` (la región de ese lado) y `area_id` (el área sin lado).
- **Waxholm:** BrainGlobe trae un volumen de hemisferios (1 = izquierdo, 2 = derecho).

## Resolución de Waxholm para C

Reducción por voto mayoritario: cada bloque toma la etiqueta que más vóxeles tiene. La variante «proteger» da a cada región que se quedaría sin vóxeles el bloque donde más tiene, siempre que eso no borre otra región.

| Resolución | NIfTI | Regiones perdidas | Con «proteger» | Región fina (cst L, 684 vóxeles a 39 µm) |
|---|---|---|---|---|
| 78 µm | 1,5 MB | CC L | ninguna | 90 |
| **117 µm** | **0,54 MB** | CC L | **ninguna** | 14 |
| 156 µm | 0,27 MB | CC L y CC R | ninguna | 5 |

**Elegido por Aday: 117 µm con «proteger».** CC L es la franja izquierda del canal central, en la línea media, con 141 vóxeles a 39 µm; con la protección queda en 1 vóxel. Fondo de RM: no se ha añadido; cabe en el presupuesto si Sofía lo pide.
