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
