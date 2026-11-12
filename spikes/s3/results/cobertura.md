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
- **Regla, medida y no elegida a mano** (`cerebra.py`): se queda una estructura de CerebrA si al menos la mitad de sus vóxeles no tienen etiqueta de Julich-Brain. Y se quedan solo esos vóxeles. Donde los dos atlas tienen algo, gana Julich-Brain, y un vóxel nunca pertenece a dos regiones.
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

## Tabla por familia (después de añadir CerebrA)

Entre paréntesis, el número de regiones sin contar el lado.

| Familia | Rata (Waxholm) | Humano, Julich-Brain | Humano, CerebrA |
|---|---|---|---|
| Corteza | sí (47) | sí (134 + 7 GapMaps) | — |
| Hipocampo | sí (6) | sí (8) | — |
| Amígdala | sí (3) | sí (7) | — |
| Ganglios basales | sí (12) | parcial (10: estriado ventral, prosencéfalo basal…) | **sí** (caudado, putamen, pálido) |
| Tálamo y subtálamo | sí (61) | sí (33) | — |
| Hipotálamo | sí (1, sin dividir) | **no** | no (dentro del diencéfalo ventral, que se queda fuera) |
| Mesencéfalo | sí (13) | parcial (sustancia negra, núcleo rojo) | sí, dentro de «Brainstem» |
| Rombencéfalo: cerebelo, puente y bulbo | sí (22) | solo los 4 núcleos del cerebelo | **sí** (cerebelo y vermis; el tronco es una sola región) |
| Sustancia blanca | sí (45 tractos) | **no** | solo la del cerebelo y el quiasma |
| Ventrículos | sí (3) | **no** | **sí** (3) |
| Bulbo olfatorio | sí (5) | **no** | no |
| Médula espinal | sí (principio) | **no** | no |
| Oído interno y nervios (cóclea, nervios coclear y vestibular) | sí | no | no |

## Lo que sigue faltando en el humano, y por qué

1. **Médula espinal.** La plantilla MNI acaba a z = −78 mm. El tronco de CerebrA llega justo hasta ese borde (`lowest_labelled_z_mm`), así que la médula queda fuera de la imagen. Ningún atlas en este espacio puede tenerla. Haría falta otra plantilla que la incluya (por ejemplo PAM50, de la médula), en otro espacio. No se ha buscado.
2. **Sustancia blanca del cerebro.** Ni Julich-Brain ni CerebrA etiquetan los tractos: cuerpo calloso, cápsula interna… En 3D no se nota, porque está por dentro. En el corte sale como hueco blanco. La rata sí los tiene.
3. **Hipotálamo.** Solo existe dentro del «diencéfalo ventral» de CerebrA, que mezcla hipotálamo, subtálamo y otras estructuras, y que la regla deja fuera porque Julich-Brain cubre más de la mitad. Rellenar solo el resto daría una mancha con un nombre que no le corresponde.
4. **Bulbo olfatorio.** No está en ninguno de los dos atlas humanos.
5. **Tronco sin dividir.** CerebrA tiene el tronco como una sola región, sin separar mesencéfalo, puente y bulbo. La rata sí los separa.

Rellenar los puntos 2 a 5 exigiría otro atlas más, y cada uno trae su licencia y su costura. Queda a decisión de Aday y de Sofía.

## Parejas nuevas (propuestas, con grado «pendiente de Sofía»)

Están en `site/data/equivalencias.json`. Son solo propuestas: si son parejas, y con qué grado, lo decide Sofía.

| Rata | Humano (CerebrA) |
|---|---|
| Cerebellum (Cb) | sustancia gris y blanca del cerebelo y los tres bloques del vermis |
| Brainstem, unspecified (BS-u) | Brainstem |
| Caudate putamen (CPu) | Caudate y Putamen |
| Pallidum (PAL) | Pallidum |
| Ventricular system (V) | ventrículos lateral, tercero y cuarto |
| optic tract and optic chiasm (opt-och) | Optic Chiasm |
