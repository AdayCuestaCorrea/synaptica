# S3 · Lo que pide Sofía tras ver las maquetas B y C

Recogido el 2026-11-11 de un documento de Sofía (2 páginas, «Cerebro 3D») y de sus respuestas a las preguntas Q1–Q7 que le pasó Aday ese mismo día. El documento original no se guarda en el repositorio: esto es un resumen con nuestras palabras. Sus imágenes de ejemplo no se copian.

## Elección

**Maqueta C (Niivue).** El documento solo comenta la «versión C» y Sofía lo confirma después (Q1). De B no quiere conservar nada que C no tenga: el clic que resalta la pieza en el otro cerebro ya está en C.

D3 la cierra Aday en el ADR `docs/adr/0003-visor.md`, después de los ajustes de este paso y de que Sofía vea el resultado.

## Peticiones

| # | Petición | Origen | Respuesta de Sofía |
|---|---|---|---|
| P1 | Corte 2D y recorte 3D sincronizados: al avanzar uno, avanza el otro | Documento, punto 1 | Q2: el 2D en **coronal**, como ahora, y el recorte 3D en **sagital**; en las dos direcciones |
| P2 | El recorte 3D sale en diagonal; tiene que ser sagital del todo | Documento, punto 2 | Q2 |
| P3 | Al clicar una pieza en un cerebro, se selecciona la correspondiente en el otro | Documento, punto 3 | Q3: además, el otro visor **gira y lleva su corte** hasta ella |
| P4 | Tres formas de ver el cerebro: color por áreas, atlas en blanco y negro, y tinción realista | Documento, punto 4 | Q4: el blanco y negro con relleno en grises **y** contornos, en 2D y probado también en 3D. Q5: la tinción, en dos versiones, una con datos reales con licencia y otra dibujada por nosotros; luego se elige. Q7: son **tres modos separados**; se elige uno |
| P5 | Una paleta de colores menos ruidosa, en 2D y en 3D | Documento, punto 5 | — |
| P6 | Al clicar, el nombre del área. Cuando exista el glosario, su definición, nombre completo y sigla al pasar por la sigla | Añadido por Aday al revisar el plan | — |
| P7 | Coordenadas en milímetros referidas a Bregma y Lambda | Las imágenes de ejemplo llevan ejes en mm y la posición respecto a Bregma | Q6: «todo basado en Bregma y Lambda y en mm» |

## Lo que ya sabíamos y cruza con esto

- **P2:** el recorte de C usa un plano girado −60° (`site/c/c.js`, `setClipPlane` con el azimut de la cámara), de ahí la diagonal.
- **P1:** un corte coronal y uno sagital son perpendiculares, así que no pueden ser el mismo corte. Aday decide probar dos variantes y descartar una al verlas:
  - **punto común:** en el 2D, una línea vertical marca dónde corta el plano sagital del 3D y se puede arrastrar; en el 3D, el plano coronal del 2D se ve como un plano fino que avanza con el corte;
  - **dos deslizadores:** uno por plano, y cada vista muestra la posición del otro.
- **P3** ya funciona, pero solo con los 3 pares de prueba de `equivalencias.json`. En C todo el atlas es clicable, así que casi cualquier toque cae en una región sin pareja y no se resalta nada. Hace falta un aviso. Las parejas reales y su grado son trabajo de Sofía en la Fase 2.
- **P5:** ahora se usan los colores oficiales de cada atlas, cientos de tonos distintos uno junto a otro.
- **P6:** el panel ya muestra el nombre. Los nombres de los dos atlas están solo en inglés; los nombres en español son contenido de la Fase 2, revisado por Sofía. La definición al pasar por la sigla es de la Fase 2 (Neuro Glossary).
- **P7:** Bregma y Lambda son puntos del cráneo de la rata. En el humano lo estándar son los milímetros del espacio MNI. La posición de Bregma y Lambda en Waxholm tiene que salir de una publicación; si no se encuentra, se deja vacía y se avisa.
- **P4, tinción:** hacen falta histologías con licencia y alineadas a cada atlas, que ahora no tenemos. La versión dibujada lleva en el propio lienzo el aviso de que es una ilustración y no una tinción real.
- **The Folded Mind (SCOPE §1):** decisión de Aday: el visor sigue abriendo en 3D y el corte 2D es la segunda vista. Los cortes son de las etiquetas del atlas, no de resonancia.
