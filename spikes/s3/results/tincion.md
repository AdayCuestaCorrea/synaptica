# S3 · Paso 7.8: tinción real (petición P4)

Hecho el 2026-11-11. La pregunta: ¿hay histología **real**, con licencia, ya **alineada** a cada atlas y que **quepa** en el peso de la web? Se ha buscado con la red solo desde la sesión de trabajo (User-Agent genérico); los tests no usan red.

## Resumen

| | Humano (Julich-Brain, MNI152 2009c) | Rata (Waxholm v4.01) |
|---|---|---|
| Encontrado | **BigBrain** en ICBM152 2009 asimétrico, 1 mm (Xiao et al. 2019) | Atlas Timm-Nissl (Blixhavn et al. 2023): cortes de Nissl registrados a Waxholm v4 |
| Tinción | Plata de Merker: tiñe los cuerpos celulares, como un Nissl | Nissl (tionina), en cortes alternos con Timm |
| Licencia | **CC BY 4.0** para las versiones reducidas (con permiso del MNI y de Jülich); BigBrain entero sigue siendo CC BY-NC-SA 4.0 | CC BY 4.0 (DataCite 10.25493/T686-7BX) |
| Alineado | Sí: la misma rejilla que nuestro mapa de Julich-Brain (193 × 229 × 193, origen −96, −132, −78) | Solo corte a corte (QuickNII + VisuAlign); no hay volumen 3D |
| Peso | 1,61 MB (`stain.nii.gz`, 8 bits) | TIFF a 0,22 µm/píxel: muchos GB |
| Decisión | **Integrado** como variante «Real» del modo Tinción | **Backlog** (SCOPE §10) |

## Humano: BigBrain en el espacio MNI

- **Fuente:** OSF, proyecto [xkqb3](https://osf.io/xkqb3/), archivo `BigBrain-to-ICBM2009asym-nonlin-1mm.nii` (34 MB, float32), del artículo de Xiao et al. 2019 en *Scientific Data* (doi 10.1038/s41597-019-0217-0). Es BigBrain (Amunts et al. 2013, *Science*, doi 10.1126/science.1235381) llevado al ICBM152 2009 asimétrico no lineal.
- **Licencia:** el proyecto de OSF es CC BY 4.0. Su README dice que las versiones reducidas de BigBrain se reparten con CC BY 4.0 con el permiso del MNI y de Forschungszentrum Jülich, y que BigBrain en sí sigue siendo CC BY-NC-SA 4.0. Las dos licencias están permitidas en SYNAPTICA. Se citan los dos artículos.
- **Alineación:**
  - el registro es al ICBM152 **2009b**, y nuestro mapa de Julich-Brain está en el **2009c**. Los dos son el mismo espacio, el 2009 no lineal asimétrico, y el archivo de 1 mm tiene exactamente la rejilla de nuestro mapa (`build_assets.py` lo comprueba y para si no coincide);
  - comprobado a ojo en y = −18 mm: los contornos de Julich-Brain caen sobre la corteza de BigBrain;
  - es otro cerebro, no el de los diez donantes del mapa de Julich-Brain, así que en cada punto la correspondencia es aproximada. El aviso del lienzo lo dice: «Tinción real de otro cerebro (BigBrain)».
- **Preparación** (`build_assets.py`, función `bigbrain()`):
  - se descarga una vez a `data/cache/s3/bigbrain/` (sin versionar);
  - pasa a 8 bits; el portaobjetos (blanco) y los vóxeles sin datos valen 0, así que salen transparentes en 3D;
  - se centra como el volumen de etiquetas del humano;
  - va en su carpeta, `site/data/bigbrain/`, con su `licence.json`. No se junta con ningún archivo de Julich-Brain: en la pantalla solo se superponen.
- **Peso:** 1,61 MB con gzip; el humano suma 2,3 MB, dentro del presupuesto de 3 MB por atlas. Con 64 niveles de gris pesaría 1,12 MB, pero no se ha probado cómo se ve.
- **En la maqueta:**
  - el modo Tinción tiene dos variantes, «Dibujada» y «Real» (`?mode=stain&stain=real`);
  - en «Real», el humano carga BigBrain la primera vez, debajo de las etiquetas, que se vuelven transparentes salvo la selección y su pareja;
  - en el corte, la selección lleva un contorno naranja;
  - la licencia y la cita de BigBrain aparecen bajo las del atlas mientras se ve;
  - el clic sigue eligiendo regiones de Julich-Brain a través de BigBrain;
  - la rata no tiene tinción real: sigue la dibujada, con el aviso «Ilustración, no es una tinción real (no hay de rata)».
- **Medido** (móvil emulado: Slow 4G, CPU ×4, gzip; `measure-c-gzip-stain-real.json` y `measure-c-gzip-color.json`, tres ejecuciones cada una):

  | | Color | Tinción real |
  |---|---|---|
  | Peso transferido | 1,958 MB | 3,574 MB (+1,62 MB, solo BigBrain) |
  | Listo para usar | 16,7–16,9 s | 16,8–17,0 s (BigBrain llega después) |
  | Otros dominios | ninguno | ninguno |

  Con Slow 4G, la tinción real tarda unos 9 s más en aparecer. En los otros modos no se descarga nada de BigBrain.

## Rata: el atlas Timm-Nissl

- **Fuente:** Blixhavn C. H. et al. 2023, *A Timm-Nissl multiplane microscopic atlas of rat brain zincergic terminal fields and metal-containing glia*, *Scientific Data* 10:150 (doi 10.1038/s41597-023-02012-6, CC BY). Hay dos conjuntos en EBRAINS, 10.25493/T686-7BX y 10.25493/4K9X-FJW, los dos CC BY 4.0 según DataCite.
- **Qué tiene:**
  - cortes de cinco ratas Wistar, mientras que Waxholm es Sprague Dawley, en tres planos;
  - la serie coronal de Nissl (tionina), H108c, tiene 146 cortes de 40 µm, escaneados a 0,22 µm/píxel y guardados como TIFF con compresión JPEG;
  - cada corte está registrado a Waxholm v4 con QuickNII (afín) y VisuAlign (no lineal), en archivos JSON.
- **Por qué no se integra ahora:** no hay un volumen 3D. Habría que descargar la serie, que pesa muchos GB, y montar un volumen en la rejilla de Waxholm a partir de los registros corte a corte, aplicando también la deformación de VisuAlign. Además, el resultado tendría huecos entre cortes y sería de otra cepa. Es trabajo de días, no de un spike.
- **Backlog:** volumen de Nissl de rata en Waxholm a partir del atlas Timm-Nissl (SCOPE §10).

## Segunda búsqueda, tras la revisión de Sofía (2026-11-12)

Sofía pidió una tinción real para la rata, porque le extrañaba que no la hubiera: lo normal es que haya más histología de rata que humana. Tiene razón en que hay mucha más, pero está en **cortes**, no en volúmenes 3D.

- **Dónde se buscó:**
  - DataCite, en todos los repositorios y en los conjuntos de EBRAINS (prefijo 10.25493): «rat» con Nissl, histología, citoarquitectura, plata, Merker o Timm, junto a 3D, volumen, plantilla o reconstrucción;
  - la web general;
  - y los recursos que ya conocíamos.

  El catálogo de EBRAINS no tiene una API pública de búsqueda, por eso se fue por DataCite.
- **Lo que hay:**
  - **Zhao, Puchades, Zilles y Palomero-Gallagher 2024**, «Regional and laminar distribution of silver stained cell bodies in the rat brain» (v2, doi 10.25493/D8NF-B83, CC BY-NC-SA 4.0): cortes coronales con una tinción de plata de los cuerpos celulares, de la misma familia que la de BigBrain, y su registro a Waxholm. Son cortes, no un volumen. Es el mejor candidato si algún día se monta uno.
  - Blixhavn 2023 (arriba), con sus coordenadas 3D por corte (doi 10.25493/QFFN-H67): son polígonos de dónde está cada corte, no imagen en 3D.
  - Schubert et al. 2016: sigue sin conjunto de datos publicado.
  - Atlas de rata en 3D que sí existen, como Waxholm, el de Fischer 344 o Sigma: son de **resonancia magnética**, no de tinción.
  - El ratón sí tiene un Nissl en 3D (Allen), pero es otra especie.
- **Por qué no hay un «BigBrain de rata»:** BigBrain fue un proyecto aparte, de años, que cortó un cerebro humano en 7404 secciones para reconstruirlo en 3D. Con la rata, los laboratorios publican series de cortes y su registro al atlas, pero nadie ha publicado el volumen reconstruido con licencia abierta.
- **Decisión:** sin cambios. La rata sigue con la tinción dibujada y su aviso. El backlog pasa a incluir a Zhao 2024 como fuente alternativa a Blixhavn.

## Descartado

- **Schubert et al. 2016** (*Front. Neuroanat.* 10:51, CC BY): citoarquitectura (plata de Merker), receptores y fibras de rata registrados a Waxholm. El artículo dice que las reconstrucciones 3D estarán en el portal del HBP, pero no da ningún enlace, formato ni licencia de los datos, y no se ha encontrado el conjunto en EBRAINS.
- **Paxinos y Watson o Swanson registrados a Waxholm** (EBRAINS): son láminas dibujadas, no histología. Las de Paxinos tienen copyright y sus imágenes no se comparten.
