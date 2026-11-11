# S3 · Pasos 5 y 6: maqueta C (Niivue con volúmenes propios)

Medido el 2026-11-11. Maqueta en `spikes/s3/site/c/`; datos del paso 3 en `spikes/s3/site/data/`; Niivue 0.69.0 (BSD-2-Clause) guardado en `spikes/s3/site/vendor/niivue-0.69.0/`, con su licencia y la de sus dependencias empaquetadas (`SOURCE.md`).

Se sirve en local con `python -m http.server 8766 --bind 127.0.0.1 --directory spikes/s3/site`, y en el móvil se ve en `mobile.html?m=c`.

## Qué hace

- Dos lienzos, rata y humano, con el mismo diseño que B. Cada uno carga el NIfTI de etiquetas de su atlas: Waxholm a 117 µm y Julich-Brain a 1 mm. **El atlas entero es clicable**, no solo las regiones de prueba.
- **Clic o toque:** el ID sale del valor del vóxel bajo el puntero. Mismo panel y mismo resaltado de la equivalente del mismo lado que en B, con «pendiente de Sofía»; el resto se vuelve gris.
- **Dos vistas:**
  - «Solo 3D»;
  - «3D + corte», con un corte coronal al lado del 3D, o debajo si el lienzo es más alto que ancho. En el corte se clica con un solo toque y se ven las estructuras internas sin trucos.
- **Estructuras internas en 3D:** «Recortar» corta el volumen por la mitad, y «Aislar selección» deja solo la región y su equivalente.
- Licencias, citas, aviso médico y los dos idiomas, como en B.

### Dos problemas de Niivue 0.69 y cómo se sortean (solo en el visor; los datos no cambian)

1. **En 3D, Niivue solo lee el vóxel con doble clic**, doble toque o pulsación larga. Un clic corto, sin arrastrar, sobre la vista 3D le manda ese doble clic.
2. **Con unas 450 etiquetas, el fondo salía opaco** con el color de la etiqueta 3. El shader sube cualquier valor por encima del mínimo a al menos 2/256 de la tabla de colores (su incidencia 1139); con tablas grandes eso cae en la entrada 3 o 4. Al cargar, las etiquetas se suben 8 valores y esas primeras entradas quedan vacías y transparentes.
   - La alternativa obvia, `colormapType = 2`, lee la tabla en el borde entre dos entradas y mezcla cada etiqueta con su vecina, que es la del otro lado. Se probó y se descartó.

## Mediciones

Mismo método que B (`spikes/s3/measure.mjs`): Chromium 157 sin interfaz, móvil de 390 × 844 con DPR 3 y táctil, «Slow 4G» y CPU ×4, 3 ejecuciones. Datos en `measure-c.json`, `measure-c-gzip.json` y `measure-c-gzip-dpr1.json` (esta, con 2 ejecuciones).

| | Sin comprimir | Con gzip en el texto (como Pages) |
|---|---|---|
| Peso transferido | 3,61 MB · 12 peticiones | **1,91 MB** · 12 peticiones |
| Hasta poder usar los dos visores | 25,3 s | **16,0–16,6 s** |

- **Reparto del peso, con gzip:** el código ocupa unos 0,81 MB, de los que Niivue son 0,80 MB (ya minificado y con sus dependencias). Los datos, unos 1,10 MB: los dos NIfTI (536 y 539 KB, ya comprimidos) y las tablas de nombres.
- **Fluidez al girar:** depende de la resolución del lienzo, porque el 3D es un trazado de rayos por píxel.

  | Resolución | CPU ×4 | CPU ×1 |
  |---|---|---|
  | DPR del móvil (3) | **3 fps** | 3–4 fps |
  | `?dpr=1` | 22 fps | 24 fps |

  Como en B, son cifras con WebGL **por software**, es decir, una cota pesimista. En el Chrome de escritorio, con la GPU real, iba a unos 42 fps solo 3D y 31 fps con el corte, en el tope de fotogramas que permite el navegador automatizado. **Falta probarlo en un móvil real.** Con `?dpr=1` se ve algo más borroso en pantallas densas.
- **Táctil:** en las 3 ejecuciones, un toque selecciona «Primary somatosensory area, face representation (S1-f)», que no está entre las equivalencias de prueba, así que no se resalta nada en el humano, como debe ser. Arrastrar gira (cambia el azimut) y pellizcar acerca (de ×1 a ×2).
- **Otros dominios:** ninguno; todo va a `127.0.0.1`. Las 2 URL internas son `data:` y `blob:` que crea Niivue. El paquete no lleva URL de red fuera de los comentarios.

## Lectura

- Cumple los requisitos duros de D3: 1,91 MB en total.
- **A favor de C:**
  - todo el atlas es clicable sin generar ni una malla, así que añadir regiones al contenido no cuesta nada;
  - el corte 2D enseña las estructuras internas de forma natural;
  - es un visor de neuroimagen ya hecho.
- **En contra:**
  - pesa casi el doble que B y tarda unos 6 s más con red lenta, sobre todo por el propio Niivue (0,80 MB);
  - el 3D por trazado de rayos es caro en pantallas densas;
  - ha hecho falta sortear dos comportamientos del propio Niivue, que pueden cambiar entre versiones.
- **Mejoras posibles, no hechas:**
  - limitar la resolución del 3D (`?dpr=1` o 2) en móviles;
  - quitar el árbol completo de `labels.json` de la rata;
  - fondo de RM: no está y cabría.

## Paso 7.2: paleta tranquila (petición P5 de Sofía)

Hecho el 2026-11-11. `build_assets.py` da a cada región una **familia** (corteza, hipocampo, bulbo olfatorio, amígdala, ganglios basales, tálamo, hipotálamo, mesencéfalo, rombencéfalo, sustancia blanca, ventrículos y otras) a partir de la jerarquía de su propio atlas, y un tono suave de esa familia, con pequeños saltos de luminosidad entre vecinas para que se vean los bordes. La misma familia tiene el mismo tono en los dos atlas, así que la rata y el humano se leen igual; cada atlas se colorea solo con sus datos.

- En `labels.json`: campos nuevos `group` y `color_calm`; el color oficial sigue en `color`. Unos 20 KB más por atlas sin comprimir. Dos ejecuciones dan archivos idénticos.
- Corteza humana: un ligero cambio de tono por lóbulo. Las *GapMaps* de Julich-Brain (corteza aún sin mapear) van en un tono casi gris.
- B y C usan la paleta nueva por defecto; con `?colors=atlas`, los colores oficiales, para comparar. La región elegida y su pareja se pintan con una versión más intensa de su tono, y el resto en gris.
- El pie de cada atlas dice que los colores son una paleta propia de SYNAPTICA.
- Comprobado en Brave (escritorio): 3D y corte coronal en los dos atlas, selección del subículo (rata) con el hipocampo humano resaltado, B con las tres regiones de prueba, español e inglés, sin errores en la consola.

## Paso 7.3: recorte sagital y corte coronal sincronizados (peticiones P1 y P2)

Hecho el 2026-11-11, solo en C.

- **Cámara y recorte sin diagonal:** la vista 3D mira el lado izquierdo de frente (azimut 90, elevación 0) y el recorte es siempre un plano **sagital**. Antes, el plano seguía a la cámara a −60°.
- **Cómo se sincronizan dos planos perpendiculares:** comparten un punto, el punto de cruce de Niivue. Su x es el recorte sagital del 3D y su y el corte coronal del 2D. En el 2D, la línea vertical marca dónde corta el 3D; en el 3D, la cruz marca dónde está el corte coronal.
- **Geometría (comprobada en el código de Niivue 0.69):** el plano de recorte es `dot(n, p − 0,5) + d = 0`, con `p` en fracciones del volumen. Con azimut 270, `n = +x`, así que el plano queda en `x = 0,5 − d` y se quita la parte del lado de la cámara. El arrastre propio de Niivue en 3D **gira** el plano, y por eso no se usa.
- **Dos variantes, para que Sofía elija:**
  - **Punto común** (por defecto): se mueve el punto haciendo clic o arrastrando en el corte 2D, o con un clic en la cara cortada del 3D.
  - **Dos deslizadores** (`?sync=deslizadores`): además, un deslizador por plano con su posición en mm. Por ahora son mm del atlas centrados en el cerebro; Bregma y Lambda llegan en el paso 7.5.
- «3D + corte» enciende el recorte, porque los dos planos van juntos; «Recortar» lo sigue quitando y poniendo.
- **Comprobado en Brave (escritorio), en los dos atlas:**
  - deslizador sagital a 0,30: recorte en `d = 0,20`, con la línea del 2D en el hemisferio izquierdo (x = −4,1 mm en la rata, −38,6 mm en el humano);
  - deslizador coronal a 0,38: el 2D pasa al cerebelo de la rata y la cruz del 3D se mueve hacia atrás;
  - clic en el 2D de la rata en x = 0,707: recorte en `d = −0,207`, y CA3 seleccionado y resaltado en el humano;
  - clic en la cara cortada del 3D humano: el corte coronal salta a y = 0,40 y el recorte se queda en x ≈ 0,51;
  - español e inglés, sin errores en la consola. Falta el móvil (paso 7.9).

### Paso 7.3, segunda parte: deslizadores con mm escritos y eje z

Decisión de Aday (2026-11-11): de las dos variantes se queda la de los **deslizadores**. La variante «punto común» se quita como opción aparte, aunque hacer clic en el corte o en la cara cortada sigue moviendo el punto.

- Tres filas, una por eje: **x** (sagital, mueve el recorte 3D), **y** (coronal, mueve el corte 2D) y **z** (vertical: mueve la línea horizontal del corte y la altura de la cruz del 3D; no hay recorte axial).
- Cada fila tiene un deslizador y un **campo para escribir los mm** exactos. Se aplica con Intro o al salir del campo. Acepta punto o coma decimal, y un valor fuera del volumen se ajusta al borde (999 → 96,50 mm en el humano). Un texto que no es número deja el valor como estaba.
- Los mm siguen siendo del atlas, centrados en el cerebro: Bregma y Lambda llegan en el paso 7.5.
- Comprobado en Brave: y = −3,5 en la rata, y = 20,5 escrito con coma en el humano, x = 999 ajustado al borde y z = «abc» sin cambios.

## Paso 7.4: clic sincronizado, nombre y sigla (peticiones P3 y P6)

Hecho el 2026-11-11, solo en C. El panel nuevo vive en `c/c.js`, no en `common/`, para no cambiar B.

- **Centroides:** `build_assets.py` guarda en `labels.json` el número de vóxeles (`voxels`) y el centroide en mm (`centroid_mm`) de cada región y lado, calculados sobre el mismo volumen y la misma transformación que carga C. Cada atlas, con sus propios datos. Sigue siendo idempotente.
- **Al hacer clic en una región con pareja**, el otro cerebro:
  - la selecciona y la colorea en tono intenso;
  - lleva el punto común (el corte coronal, el recorte sagital y la cruz) a su centroide, ponderado por vóxeles cuando la pareja son varias áreas (el hipocampo humano son 5);
  - en «Solo 3D» gira la cámara hacia el lado de la región. Con el recorte puesto, la cámara se queda a la izquierda, porque el recorte quita ese lado y la región aparece en la cara cortada;
  - en su panel dice «Pareja de CA1 (rata)», con las áreas, el hemisferio y el grado «pendiente de Sofía».
- **Sin pareja:** el panel de la región elegida dice «sin pareja todavía en el otro cerebro» y el del otro cerebro, «LP-mc (rata) aún no tiene pareja en este cerebro».
- **Nombre y sigla (P6):** el panel empieza por la sigla y el nombre completo («CA1 · Cornu ammonis 1»). Para Julich-Brain, la sigla es lo que va antes del paréntesis («CA3 (Hippocampus)» → «CA3»). Además, junto al punto tocado aparece una etiqueta con los dos, que se oculta al arrastrar.
- **Gancho para el glosario (Fase 2):** cada sigla va en `<abbr data-glossary="CA1" title="Cornu ammonis 1">`.
- **Nombres en español:** los atlas solo traen nombres en inglés. En la versión en español, el panel lo avisa («la traducción la revisa Sofía en la Fase 2»); no se traduce a ojo.
- **Las estructuras internas** (amígdala, hipocampo) no se ven en «Solo 3D» aunque la cámara gire hacia ellas, porque la corteza las tapa. Se ven con el recorte o con «Aislar selección».
- **Comprobado en Brave:**
  - un clic en el corte de la rata sobre una región sin pareja (LP-mc, cuerpo calloso): etiqueta junto al punto y avisos en los dos paneles;
  - CA1 derecho de la rata → hipocampo derecho humano en x = 26, z = −36 mm, con su panel;
  - área 4a izquierda humana → M1 izquierda de la rata (x = −3,56 mm);
  - Am-u derecha en «Solo 3D» → el humano gira a 270°;
  - español e inglés, sin errores en la consola.
  - Las selecciones de pareja se lanzaron desde la consola, para elegir exactamente la región; el clic con el ratón se probó aparte.

## Paso 7.5: coordenadas en mm desde Bregma y MNI (petición P7)

Hecho el 2026-11-11, solo en C.

- **Fuente de Bregma y Lambda:** E. A. Papp y J. G. Bjaalie, *Waxholm Space atlas of the Sprague Dawley rat brain. Coordinates v1 vs v1.01*, Neural Systems Laboratory, 16 de julio de 2014, en NITRC ([PDF](https://www.nitrc.org/docman/view.php/1081/2095/Coordinates_v1-v1.01.pdf)). Para la versión v1.01 a 39 µm da, en vóxeles (desde 0) y en mm WHS (origen en la decusación de la comisura anterior):

  | Punto | Vóxel (x, y, z) | mm WHS (x, y, z) |
  |---|---|---|
  | Origen WHS | 244, 623, 248 | 0, 0, 0 |
  | Bregma | 246, 653, 440 | 0,078; 1,172; 7,500 |
  | Lambda | 244, 442, 464 | 0; −7,070; 8,438 |

  Se guardan solo esas cifras (fixture `tests/fixtures/s3/whs_coordinates_v1_01.json`), no el documento.
- **¿Vale para v4.01?** La tabla es de v1.01, pero las versiones siguientes cambian las delineaciones, no la rejilla: el volumen de BrainGlobe sigue siendo de 512 × 1024 × 512 y su vóxel (244, 623, 248) cae en la comisura anterior (rama anterior, con la posterior al lado), que es donde la tabla pone el origen.
- **Conversión** (`spikes/s3/coords.py`): de los mm del visor (centrados en el volumen) a mm desde Bregma, pasando por el vóxel de 39 µm. BrainGlobe dice que el vóxel mide 39,0 µm y la tabla, 39,0625 µm; se usa el de la tabla (un 0,16 % de diferencia, unos 0,02 mm cada 10 mm). El humano: mm MNI152 2009c, que son los mm del visor más el centro del volumen. `build_assets.py` escribe un `coords.json` por atlas.
- **Cráneo plano (opción A, decisión de Aday).** En el animal del atlas, Lambda está 0,94 mm más alto que Bregma; en Paxinos y Watson están a la misma altura (*flat skull*). Sin corregirlo, un corte coronal del visor estaría inclinado 6,5° respecto a una lámina: unos 1,1 mm de AP de diferencia entre arriba y abajo en 10 mm de alto. Por eso `build_assets.py` gira las etiquetas a 39 µm alrededor del eje izquierda-derecha, con Bregma como pivote, el ángulo que deja Lambda a la altura de Bregma: atan(0,9375 / 8,2422) = **6,49°**. El giro sale solo de los dos puntos publicados.
  - Vecino más próximo sobre una rejilla de 39,0625 µm ya en mm desde Bregma; después se reduce a 117 µm como antes.
  - Ninguna región se pierde; cada una conserva entre el 98,9 % y el 101,5 % de sus vóxeles. El NIfTI pasa de 536 KB a 549 KB (172 × 355 × 186 vóxeles).
  - Lambda queda en AP −8,30 mm y DV 0. La distancia Bregma–Lambda se conserva.
  - Un giro alrededor de x deja los planos sagitales como sagitales: el recorte 3D no cambia.
  - Es un dato derivado del mismo atlas (CC BY 4.0); no se junta con nada de Julich-Brain.
- **En la maqueta:**
  - los deslizadores de la rata pasan a ser ML (x), AP (y) y DV (z) en mm desde Bregma; los del humano, mm MNI. Escribir −3,6 en AP lleva el corte coronal a Bregma −3,60 mm;
  - sobre el corte 2D, marcas en mm (x abajo, z a la izquierda, con el 0 más largo) y, arriba, la posición del corte: «Bregma −3,60 mm · Lambda +4,64 mm» en la rata y «y = −20,0 mm (MNI)» en el humano;
  - bajo los deslizadores, qué son esos mm, que el atlas se ha girado 6,5° para que el cráneo quede plano, dónde está Lambda (AP −8,30 mm) y la fuente con su enlace.
- **Avisos:**
  - son las coordenadas del animal del atlas; en otra rata son aproximadas, y así se dice en la página;
  - el DV se mide desde la altura de Bregma (sobre el cráneo), no desde la superficie del cerebro.
- **Comprobado en Brave (escritorio):** con el punto en Bregma, los tres campos dan 0,00; con AP −3,60 y DV −5,00, la cruz del 2D cae en las marcas −5 de z y 0 de x, el hipocampo dorsal está en el corte, la superficie del cerebro queda a unos −1 mm y la base a unos −10 mm; en el humano, y = −20 mm MNI. Con el cráneo plano, Lambda da (−0,08; −8,30; 0,00). Al elegir CA1 derecho en el humano, el centroide del hipocampo de la rata cae en ML +3,84, AP −4,94 y DV −5,42. En «Solo 3D» las marcas desaparecen. Español e inglés, sin errores en la consola. Dos ejecuciones del script dan archivos idénticos.
- **Test** (`uv run pytest spikes/s3/tests`, sin red): la tabla publicada cumple la fórmula; con el cráneo plano, Bregma da 0, Lambda queda a la altura de Bregma con la misma distancia (−8,2953 mm), el giro es de 6,489° y se deshace; y los mm del visor dan los de la rejilla plana.

## Paso 7.6: selector de modos y atlas en blanco y negro (petición P4)

Hecho el 2026-11-11, solo en C.

- **Selector «Color · Atlas · Tinción»**, un modo a la vez. «Tinción» está desactivado hasta el paso 7.7. Con `?mode=atlas` la página abre en el modo Atlas (sirve para medir).
- **Modo Atlas:** relleno en grises claros, sacados de la luminosidad del color de cada región en la paleta tranquila (de 175 a 238 sobre 255); la selección y su pareja, en un gris oscuro (125); contornos casi negros (40).
- **Contornos en 2D:** líneas finas dibujadas sobre el corte coronal, en el mismo lienzo que las marcas en mm, por las caras de vóxel entre dos regiones (o entre una región y el fondo). Solo se miran los vecinos del propio corte, así que un borde paralelo al corte no aparece como una mancha. Con «Aislar selección», solo los contornos de lo que se ve.
- **Contornos en 3D:** los vóxeles de borde se marcan en el propio volumen (la región r pasa a r + N) y la tabla de colores los pinta oscuros. En el modo Color esas entradas llevan el color de su región, así que las marcas no se ven. Detalles:
  - se marca un solo lado de cada borde, para que las líneas tengan un vóxel de grosor;
  - se miran los vecinos en y y en z (cara cortada sagital y superficie lateral) y, solo en la superficie exterior, también en x. Así la cara cortada no tiene manchas;
  - el plano coronal bajo el corte 2D se deja sin marcas mientras se ve el corte, y se restaura al moverlo. Si no, los bordes a lo largo de y saldrían como manchas en el 2D.
- **Niivue ya tiene un contorno de atlas** (`setAtlasOutline`), pero no sirve aquí. Mira los seis vecinos, así que en el 2D salen manchas, y cuenta el fondo como vecino, así que en 3D pinta de negro toda la superficie.
- **Sin archivos nuevos.** Los contornos se calculan en el navegador, a partir del mismo volumen de etiquetas, la primera vez que se elige el modo Atlas. Así no hay ningún dato derivado nuevo que licenciar y nunca se juntan los dos atlas: cada visor trabaja solo con su volumen.
- **Mediciones** (`QUERY=?mode=atlas`, móvil emulado con Slow 4G, CPU ×4 y gzip; `results/measure-c-gzip-color.json` y `measure-c-gzip-atlas.json`, tres ejecuciones cada una):

  | | Modo Color | Modo Atlas |
  |---|---|---|
  | Peso transferido | 1,954 MB | 1,954 MB (+0 bytes) |
  | Listo para usar | 16,6–16,8 s | 17,4–17,5 s |
  | Cálculo de los contornos (CPU ×4) | — | rata 377–484 ms · humano 184–194 ms |
  | Peticiones a otros dominios | ninguna | ninguna |

  - El código de C crece 2,6 KB con gzip (`c.js`, de 9,6 a 11,9 KB).
  - Respecto al paso 6 (1,914 MB), la página pesa 40 KB más por los pasos 7.2–7.6 (centroides, `coords.json` y código).
  - En escritorio, los contornos se calculan en 89 ms (rata) y 80 ms (humano). Mover el corte coronal en el modo Atlas tarda unos 53 ms, porque Niivue vuelve a subir el volumen entero a la GPU. Con la CPU ×4 será más; se mide en el paso 7.9.
  - La fluidez al girar no cambia (los mismos 3 fps a DPR 3 con WebGL por software).
- **Comprobado en Brave (escritorio):**
  - en Solo 3D y en 3D + corte, los dos atlas en grises con contornos en el 3D, en la cara cortada y en el corte 2D, que parece una lámina de atlas;
  - sin manchas en el corte al moverlo;
  - el clic en el corte elige la región (SUB) y el humano resalta su pareja en gris oscuro;
  - «Aislar» deja en el 3D solo la selección y, en el 2D, sus contornos;
  - al volver a Color no queda rastro de los contornos;
  - en español y en inglés, sin errores en la consola.
- **Ya pasaba antes, no es nuevo:** con «Aislar», el corte 2D sigue mostrando las demás regiones en gris (también en el modo Color).

## Paso 7.7: tinción dibujada (petición P4)

Hecho el 2026-11-11, solo en C.

- **Modo «Tinción»** del selector (se abre directamente con `?mode=stain`). Es una ilustración con aspecto de tinción de Nissl (violeta de cresilo), generada a partir de las etiquetas. No sale de ninguna histología.
- **Aviso en el propio lienzo**, «Ilustración, no es una tinción real» (en inglés, «Illustration, not a real stain»). Va arriba a la izquierda de la vista 3D y del corte 2D, en los dos cerebros y en las dos vistas, con fondo propio para que se lea sobre cualquier color.
- **Cuánto tiñe cada región:** lo decide el dibujo, no una medida (`STAIN` en `c/c.js`). Hay que leerlo como una propuesta para que la revise Sofía.
  - Según la familia de la paleta tranquila: hipocampo 0,75; olfativo 0,65; corteza, amígdala e hipotálamo 0,6; tálamo 0,55; ganglios basales y mesencéfalo 0,5; rombencéfalo 0,48; sustancia blanca 0,1; ventrículos 0.
  - Algunos nombres lo cambian: capas moleculares y capa 1, pálidas (0,22); giro dentado, capas granulares, capa 2 y cerebelo sin especificar, oscuros (0,9); capa glomerular, 0,35.
  - Más una variación fija de ±0,08 por región, para que se distingan las vecinas de una misma familia.
- **En 2D** se pinta el corte coronal en un lienzo encima del de Niivue:
  - la densidad se mezcla entre los centros de los vóxeles, así que los bordes son suaves;
  - el grano es de tres «células» por vóxel, atado a la rejilla, así que no parpadea al redibujar;
  - se pinta a 1,5 píxeles por píxel CSS como máximo y luego se escala, para no penalizar los móviles;
  - como tapa el corte de Niivue, la cruz se vuelve a dibujar encima y la selección y su pareja se marcan con un contorno naranja;
  - en escritorio, pintarlo tarda unos 8 ms.
- **En 3D**, cada región toma un tono plano entre el blanco del portaobjetos y el violeta, según su densidad. La selección y su pareja, en su color intenso.
- **En el humano, la sustancia blanca no está etiquetada** en el mapa de Julich-Brain: sale del color del portaobjetos, igual que el fondo, y no se ve el contorno del cerebro. En la rata sí está etiquetada y sale pálida, como en una tinción de verdad.
- **Peso:** ningún archivo nuevo. El código de C crece 2,1 KB con gzip (`c.js`, de 11,9 a 14,0 KB).
- **Comprobado en Brave (escritorio):**
  - Solo 3D y 3D + corte, con el aviso visible en los cuatro sitios;
  - a Bregma −3,6 mm, el cuerpo calloso sale pálido, el hipocampo oscuro y la corteza intermedia;
  - el clic en CA1 de la rata contornea la pareja en el corte del humano y la resalta en su 3D;
  - al volver a Color no queda nada pintado;
  - en español y en inglés, sin errores en la consola.

## Mejora M1: buscador de áreas (Aday)

Hecho el 2026-11-11, solo en C. Decisiones de Aday: un buscador por cerebro, y cada resultado resalta los dos hemisferios.

- **Dónde:** un campo encima de cada visor que busca solo en su atlas. Busca por sigla o por nombre (en inglés, como los atlas), sin distinguir mayúsculas ni tildes.
- **Orden de los resultados:** sigla exacta, sigla que empieza igual, nombre que empieza igual y, por último, coincidencia en cualquier parte. Como mucho 8.
- **Qué se puede buscar:**
  - un resultado por área, con los dos lados juntos;
  - en la rata, también los nodos padre de la jerarquía de Waxholm (por ejemplo «HF · Hippocampal formation» o «HR · Hippocampal region»), que resaltan todas sus piezas.
- **Uso:** con flechas, Intro y Escape, o con clic o toque. Si no hay nada, «Sin resultados».
- **Al elegir** se comporta como un clic: resalta el área, lleva el punto, el corte y el recorte a ella, y el otro cerebro marca su pareja (también en los dos lados) con su panel.
  - Con los dos lados, el punto va al lado izquierdo, el que mira la cámara; el centroide de los dos caería en la línea media.
  - Los paneles dicen «ambos hemisferios».
- **Comprobado en Brave (escritorio):**
  - «ca1» en el humano: CA1 a los dos lados, y la rata resalta HF a los dos lados;
  - «hipp» en la rata, flecha abajo e Intro: HF, con 12 piezas resaltadas, y el humano resalta CA1, CA2, CA3, DG y Subc;
  - «zzz»: «Sin resultados»; Escape cierra la lista;
  - en inglés, «m1»: M1 y su pareja, Area 4a y Area 4p;
  - sin errores en la consola.

