# Neuro Lab: técnicas y MeSH (medida B1)

Medido el 2026-11-17 (SCOPE v201) con [`spikes/neuro-lab/mesh_measure.py`](../../spikes/neuro-lab/mesh_measure.py). Datos: almacén reconstruido de la rama `data` (f122926), con 5059 estudios de neurociencia que no son ruido. De ellos, 2081 tienen MeSH (PubMed o Europe PMC). Solo recuentos: no se publica ni se guarda ningún texto. Sin LLM.

**Pregunta.** ¿Qué técnicas de SCOPE §4 tienen descriptor MeSH propio y cuáles irían solo por texto? ¿Cuántos estudios recientes encuentra cada vía?

## Descriptores

Se buscaron por sus términos de entrada en el SPARQL de la NLM, en todo MeSH y no solo en *Investigative Techniques*: el EEG está en E01.370.376 y la RM en E01.370.350.

| Técnica | Descriptor MeSH | ¿Propio? |
|---|---|---|
| Perfusión (transcardiaca) | ninguno | no: solo texto |
| Western blot | Blotting, Western (D015153) | sí |
| Inmunofluorescencia | Fluorescent Antibody Technique (D005455) y sus 2 hijos | sí |
| Microscopía confocal | Microscopy, Confocal (D018613) | sí |
| Electrofisiología | Patch-Clamp Techniques (D018408). *Electrophysiology* (H01) es una disciplina y *Electrophysiological Phenomena* (G07) son fenómenos, no técnicas | solo una parte |
| EEG | Electroencephalography (D004569) y Electrocorticography (D000069280) | sí |
| fMRI | Functional Neuroimaging (D059907, incluye PET) o Magnetic Resonance Imaging (D008279, incluye la RM estructural) | no: más amplios |
| Trazado con vectores virales | Neuroanatomical Tract-Tracing Techniques (D056347, cualquier trazador) | no: más amplio |
| Optogenética | Optogenetics (D062308) | sí |
| DREADDs y quimiogenética | Chemogenetics (D000098972) | sí |
| Fiber photometry | ninguno (*Photometry* es química analítica) | no: solo texto |

## Estudios que encuentra cada vía

«MeSH»: el estudio lleva el descriptor o uno que cuelga de él. «Texto»: título o palabras clave (sin resumen; la caché de resúmenes solo existe en Actions).

| Técnica | MeSH | Texto | Las dos | Solo texto, estudio sin MeSH |
|---|---:|---:|---:|---:|
| EEG | 62 | 137 | 33 | 104 |
| fMRI | 61 | 80 | 20 | 53 |
| Electrofisiología | 0 | 36 | 0 | 26 |
| Optogenética | 7 | 8 | 3 | 5 |
| Quimiogenética | 3 | 8 | 2 | 4 |
| Fiber photometry | — | 5 | — | 5 |
| Microscopía confocal | 3 | 3 | 2 | 1 |
| Western blot | 2 | 0 | 0 | 0 |
| Trazado viral | 0 | 1 | 0 | 1 |
| Inmunofluorescencia | 0 | 0 | 0 | 0 |
| Perfusión | — | 0 | — | 0 |

## Qué dice

- **Las técnicas de imagen y registro** (EEG, fMRI, electrofisiología) tienen estudios de sobra, pero **el texto encuentra más que MeSH**. Hay dos motivos: muchos estudios recientes aún no tienen MeSH (solo el 41 % lo tiene), y para fMRI y electrofisiología no existe un descriptor exacto. Hace falta la vía de texto, como en Neuro Atlas.
- **Optogenética, quimiogenética y fiber photometry** se pueden llenar, aunque con pocos estudios (5–8 en este almacén).
- **Las técnicas de banco** (perfusión, western blot, inmunofluorescencia, confocal, trazado viral) casi nunca salen en el título ni en los MeSH de estudios tan recientes, porque se describen en los métodos. Con título y MeSH su ficha quedaría con 0–3 estudios. Para llenarlas haría falta leer el resumen (la caché de Actions, como la regla de 2 menciones de Neuro Atlas, v193) o el texto completo en acceso abierto. Antes habría que medir cuánto ganan.

## Encontrado de paso

`atlas.studies.fetch` no devolvía el descriptor del propio árbol, solo los que cuelgan de él. Las etiquetas de los árboles en MeSH llevan idioma (`"…"@en`), así que `?tn = "A08.186.211"` nunca se cumplía. Arreglado con `STR(?tn)` (v201). En Neuro Atlas faltaba el descriptor *Brain*, que ninguna pareja usa. El vocabulario guardado no se ha regenerado: `syn atlas mesh` se lanza a mano, y el único cambio sería añadir *Brain*.

## B2, paso 1: las fichas (v202)

Aday eligió la opción A: MeSH y texto, con un hueco donde no hay estudios.

- **Tabla.** `src/synaptica/lab/technique_terms.toml` es una propuesta para Sofía, como `region_terms.toml`.
  - Para cada técnica guarda sus descriptores MeSH y sus palabras.
  - Las palabras son literales, sin mayúsculas y con plural, para que Sofía las pueda leer.
  - `exclude` quita lo que cuelga de un descriptor sin ser la técnica: los ritmos cerebrales bajo el EEG, los inmunoensayos bajo la inmunofluorescencia y la citometría bajo la confocal.
- **Regla distinta a la de las regiones.** Una técnica se busca en el texto de todos los estudios, tengan MeSH o no. La B1 mostró que MeSH casi nunca indexa los métodos de los registros recientes.
- **Por qué la web cuenta más que esta tabla.** El resumen cuenta cuando nombra la técnica dos veces, y solo se lee de la caché privada, que existe en Actions. La medida B (cuánto aportan los resúmenes) sale del log de `syn site` del run diario, comparada con la tabla de abajo.

| Técnica | Estudios (local, sin resúmenes) | Por MeSH | Solo por texto |
|---|---:|---:|---:|
| EEG | 156 | 56 | 100 |
| fMRI | 73 | 0 | 73 |
| Electrofisiología | 28 | 0 | 28 |
| Optogenética | 12 | 7 | 5 |
| Quimiogenética | 9 | 3 | 6 |
| Fiber photometry | 5 | 0 | 5 |
| Microscopía confocal | 4 | 3 | 1 |
| Western blot | 2 | 2 | 0 |
| Perfusión | 0 | 0 | 0 |
| Inmunofluorescencia | 0 | 0 | 0 |
| Trazado viral | 0 | 0 | 0 |
