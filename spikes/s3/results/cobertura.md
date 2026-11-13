# S3 · Revisión de Sofía: qué tiene cada cerebro

Hecho el 2026-11-12. **Por qué:** Sofía vio que al humano le faltaban el cerebelo entero, el tronco del encéfalo y el principio de la médula. Aday sospechó que también podían faltar otras partes.

**Cómo se mide.** Los dos atlas ya clasifican sus regiones en las mismas familias: las de la paleta calmada de `build_assets.py`, con las mismas reglas para los dos. La comparación se hace por familia y sobre los mismos archivos que carga el visor, sin emparejar a mano. Script: `coverage.py`. Datos: `cobertura.json`.

## Por qué faltaban

Julich-Brain v3.1 es un atlas **citoarquitectónico**: delimita áreas a partir de cortes histológicos de diez cerebros. Cubre la corteza, el tálamo, la amígdala, el hipocampo y algunos núcleos. No tiene:
- la corteza del cerebelo (solo sus 4 núcleos profundos);
- el puente ni el bulbo;
- casi nada del caudado (92 % sin etiqueta), del putamen (81 %) ni del pálido (96 %);
- los ventrículos.

El visor solo dibuja lo que tiene etiqueta, así que esas partes no se veían.

## La solución: CerebrA debajo de Julich-Brain

- **Qué es CerebrA:** Manera et al. 2020. Son las etiquetas de Mindboggle-101 registradas al MNI-ICBM2009c y corregidas a mano.
- **Rejilla:** idéntica a la de Julich-Brain y BigBrain (193 × 229 × 193 a 1 mm, mismo origen), así que no hay que remuestrear.
- **Regla, medida y no elegida a mano** (`layers.py`): se queda una estructura de CerebrA si al menos la mitad de sus vóxeles no tienen etiqueta de Julich-Brain. Y se quedan solo esos vóxeles. Donde los dos atlas tienen algo, gana Julich-Brain, y un vóxel nunca pertenece a dos regiones.
- **Entran 13 estructuras:**
  - tronco del encéfalo;
  - sustancia gris y sustancia blanca del cerebelo;
  - vermis I–V, VI–VII y VIII–X;
  - caudado, putamen y pálido;
  - ventrículos lateral, tercero y cuarto;
  - quiasma óptico.
- **Se quedan fuera** (`cobertura.json`, `cerebra_left_out`):
  - toda la corteza de CerebrA, porque Julich-Brain la cubre;
  - el hipocampo, la amígdala y el tálamo;
  - el diencéfalo ventral, con un 43 % libre;
  - el cuerno temporal del ventrículo, con un 26 % libre.
- **Para quien use la web hay un solo cerebro humano.** Los dos archivos van por separado, cada uno con su licencia, y el visor los superpone en pantalla. El panel dice de qué atlas viene cada región.
- **Licencia:** el repositorio de CerebrA es CC0 1.0, pero sus etiquetas salen de Mindboggle-101, que es CC BY-NC-SA 3.0. Se registran las dos y se sigue la más estricta, que SYNAPTICA admite.
- **Aproximación:** CerebrA se hizo sobre la plantilla MNI 2009c simétrica y Julich-Brain sobre la asimétrica. Es el mismo espacio, pero no exactamente el mismo cerebro promedio. En la costura entre los dos puede haber 1–2 mm de desajuste.
- **Peso:** +164 KB. En móvil emulado (Slow 4G, CPU ×4) la página tarda 17,2 s en estar lista, frente a 16,8 s antes (`measure-c-gzip-cerebra.json`). No se usan otros dominios.

## Segunda ronda: CIT168 y la sustancia blanca (Aday, 2026-11-12)

Aday pidió buscar otro atlas para los huecos que dejaba CerebrA. La misma regla se aplica por capas, en este orden: Julich-Brain, después CerebrA, después CIT168 y por último la sustancia blanca. Cada capa solo etiqueta lo que dejan vacío las anteriores. Un test comprueba con los archivos publicados que nunca se solapan.

- **CIT168** (Pauli, Nili y Tyszka 2018; OSF jkzwp; **CC BY 4.0**):
  - es un atlas de núcleos subcorticales en el MNI 2009c asimétrico, con la misma rejilla que Julich-Brain;
  - entran el hipotálamo (64 % libre), los núcleos mamilares (56 %) y la habénula (69 %);
  - el resto de sus 16 núcleos ya lo cubren Julich-Brain o CerebrA;
  - no distingue lados, así que se separan por la línea media (x = 0).
- **Sustancia blanca del cerebro:** es el mapa de tejidos de la propia plantilla ICBM 2009c asimétrica. Se toman los vóxeles donde la sustancia blanca es el tejido más probable (≥ 0,5).
  - **Licencia:** el aviso de McGill permite usar, copiar, modificar y distribuir siempre que se conserve el aviso de copyright; se muestra en el pie.
  - Es una sola región por lado, sin dividir en tractos. Los tractos existen con licencia CC BY 4.0: el atlas ENIGMA de 65 haces, sacado de HCP-1065. Pero son fibras de tractografía (525 MB) en la plantilla 2009a, y convertirlas en etiquetas por vóxel exige decidir qué haz gana donde se cruzan. Queda en el backlog.
- **Peso de las cuatro capas humanas:** 1,22 MB comprimidos (Julich-Brain 0,69, CerebrA 0,16, CIT168 0,08 y sustancia blanca 0,29), dentro de los 3 MB. Con todo, en el móvil simulado:
  - la descarga pasa de 1,96 a 2,49 MB;
  - la página tarda en estar lista 19,3 s en vez de 16,8 s (`measure-c-gzip-capas.json`);
  - no se usan otros dominios.

  La sustancia blanca es la capa que más pesa.

## Tabla por familia (con las cuatro capas)

Entre paréntesis, el número de regiones sin contar el lado.

| Familia | Rata (Waxholm) | Humano | De qué atlas |
|---|---|---|---|
| Corteza | sí (47) | sí (134 + 7 GapMaps) | Julich-Brain |
| Hipocampo | sí (6) | sí (8) | Julich-Brain |
| Amígdala | sí (3) | sí (7) | Julich-Brain |
| Ganglios basales | sí (12) | sí (13) | Julich-Brain y CerebrA (caudado, putamen, pálido) |
| Tálamo, subtálamo y epitálamo | sí (61) | sí (34) | Julich-Brain y CIT168 (habénula) |
| Hipotálamo | sí (1, sin dividir) | **sí** (2: hipotálamo y mamilares) | CIT168 |
| Mesencéfalo | sí (13) | parcial: sustancia negra y núcleo rojo, más el resto dentro de «Brainstem» | Julich-Brain y CerebrA |
| Rombencéfalo: cerebelo, puente y bulbo | sí (22) | sí, con el tronco en una sola región | Julich-Brain (núcleos del cerebelo) y CerebrA |
| Sustancia blanca | sí (45 tractos) | **sí, sin tractos** (cerebro, cerebelo y quiasma) | ICBM 2009c y CerebrA |
| Ventrículos | sí (3) | sí (3) | CerebrA |
| Bulbo olfatorio | sí (5) | **no** | — |
| Médula espinal | sí (principio) | **no** | — |
| Oído interno y nervios | sí | no | — |

## Lo que sigue faltando en el humano, y por qué

1. **Médula espinal.** La plantilla MNI acaba a z = −78 mm y el tronco de CerebrA llega justo hasta ese borde, así que la médula queda fuera de la imagen.
   - La plantilla que la tiene es **PAM50** (De Leener et al. 2018), compatible con el espacio ICBM152 en el tronco. Pero es otra rejilla (0,5 mm) que sigue hacia abajo.
   - Habría que ampliar la rejilla del humano y coser las dos plantillas.
   - Su repositorio no declara licencia; el de su software (SCT) es LGPL-3.0. Antes de usarla habría que confirmar la licencia de los datos.
   - Queda en el backlog.
2. **Tronco sin dividir** en mesencéfalo, puente y bulbo. La división que existe en este espacio, la de FreeSurfer (Iglesias et al. 2015, en el ICBM 2009c simétrico), **no tiene licencia publicada**, ni en la página ni en el archivo. Sin licencia no se puede usar. Otras opciones (Brainstem Navigator) tienen una licencia propia restrictiva o ya no se pueden descargar.
3. **Bulbo olfatorio.** No hay ningún atlas en el espacio MNI que lo etiquete. La plantilla apenas lo recoge, porque es muy fino y está bajo el lóbulo frontal.
4. **Tractos de la sustancia blanca:** ver ENIGMA, arriba.

## Parejas nuevas (propuestas, con grado «pendiente de Sofía»)

Rata ↔ humano. Están en `site/data/equivalencias.json`. Son solo propuestas: si son parejas, y con qué grado, lo decide Sofía.

| Rata | Humano |
|---|---|
| Cerebellum (Cb) | sustancia gris y blanca del cerebelo y los tres bloques del vermis |
| Brainstem, unspecified (BS-u) | Brainstem |
| Caudate putamen (CPu) | Caudate y Putamen |
| Pallidum (PAL) | Pallidum |
| Ventricular system (V) | ventrículos lateral, tercero y cuarto |
| optic tract and optic chiasm (opt-och) | Optic Chiasm |
| Hypothalamus (HY) | Hypothalamus (HTH) y Mammillary nucleus (MN), de CIT168 |
| Epithalamus (Thal-EPI) | Habenular nuclei (HN), de CIT168 |
| White matter (wmt) | Cerebral white matter, de ICBM 2009c |
