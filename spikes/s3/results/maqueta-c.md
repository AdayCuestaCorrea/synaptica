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
