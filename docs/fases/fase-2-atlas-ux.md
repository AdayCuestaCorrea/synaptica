# Fase 2 · Estudio de UX y UI de Neuro Atlas

> **Estado: borrador del 2026-11-15** (rama `fase-2`). Aday ha decidido UX-1–UX-6 (2026-11-15, las opciones recomendadas). UX-4 cambia una petición de Sofía y queda pendiente de que ella la confirme. Faltan sus respuestas a las preguntas del apartado 8. No hay código del visor todavía.
>
> **Cómo leerlo:** los apartados 1–5 y 8 están escritos para Sofía, sin tecnicismos. Los apartados 6, 7 y el anexo son para Aday.

**Maquetas** de estas decisiones para Sofía (pantallas estáticas, no el visor): [`spikes/atlas-ux/`](../../spikes/atlas-ux/README.md) (v157).

**Fuentes:** [notas de UX de S3](../../spikes/s3/results/notas-ux.md) · [peticiones de Sofía](../../spikes/s3/results/peticiones-sofia.md) · maquetas [A](../../spikes/s3/results/maqueta-a.md), [B](../../spikes/s3/results/maqueta-b.md) y [C](../../spikes/s3/results/maqueta-c.md) · [ADR D3](../adr/0003-visor.md) · [cobertura](../../spikes/s3/results/cobertura.md) y [tinción](../../spikes/s3/results/tincion.md) · `SCOPE.md` §4 y §7 (Neuro Atlas) · [propuesta](../propuesta.md) · el prototipo publicado (`/spikes/s3/c/`, revisado en Chrome de escritorio el 2026-11-15).

## 1. De dónde partimos

Hoy la portada enlaza a un **prototipo**: dos cerebros, rata y humano, que se pueden girar y cortar, con todas sus regiones clicables. Sofía lo eligió y lo dio por bueno. Funciona, pero se hizo para decidir **qué visor usar**, no para que lo use alguien que llega por primera vez. Lo que ya sabemos que hay que mejorar:

| Lo que pasa hoy | Por qué molesta |
|---|---|
| Una fila de 9 botones arriba (vista, recortar, aislar, tres modos, dos tinciones) y tres barras de milímetros debajo de cada cerebro | Quien llega no sabe por dónde empezar; en el móvil los botones ocupan varias líneas |
| Los nombres de las regiones solo en inglés, y con el código del atlas a la vista (`JULICH_BRAIN_…_LEFT`) | El público es hispanohablante y no técnico |
| Al tocar una región solo aparece su nombre y sus códigos | Falta lo que promete la sección: qué hace, enfermedades relacionadas, estudios recientes, técnicas |
| Casi todo lo que se toca da «sin pareja todavía» (solo hay 12 parejas de prueba) | La comparación rata ↔ humano, lo que nos diferencia, apenas se ve |
| Al elegir una región, el otro cerebro gira solo para enseñar la pareja | Si lo estabas mirando, parece que «se reinicia»; en el móvil puede girar fuera de la pantalla |
| Las estructuras internas (hipocampo, amígdala) no se ven en 3D sin recortar | Son justo las que más interesan |
| «Aislar selección» deja sola la región en 3D, pero el corte sigue enseñándolo todo | Incoherente |
| La etiqueta con el nombre sale al hacer clic, pero no al elegir con el buscador ni con las barras | Incoherente |
| Las licencias y citas, enteras bajo cada cerebro (en el humano, cinco bloques) | Ocupan media pantalla; necesarias, pero no ahí |
| Unos 19 s hasta poder usarlo en un móvil con red lenta, sin nada que leer mientras | Mucha espera en blanco |
| Al tocar una región en el móvil tarda un poco en responder | Se nota, sobre todo en móviles peores que el de Aday |

Lo que **funciona y se conserva**: todo el atlas clicable, la paleta tranquila, el corte 2D sincronizado (coronal) con el recorte 3D (sagital), los tres modos (color, atlas en blanco y negro, tinción dibujada o real), los milímetros desde Bregma en la rata y MNI en el humano, el buscador y el punto de los tres ejes.

## 2. Quién lo usa y qué busca

Los dos públicos de SYNAPTICA:

- **Curiosos sin formación:** quieren ver el cerebro, tocar una zona y entender en dos frases qué hace. No saben qué es una sigla ni un corte coronal.
- **Estudiantes:** buscan una región concreta, quieren ver dónde está en un corte, su nombre oficial, su sigla, cómo se llama en la rata y qué se ha aprendido en cada especie.

Regla de diseño que se deduce: **lo sencillo, a la vista; lo de estudiante, a un toque.** Nada de lo que hoy tiene el prototipo se quita, pero no todo se enseña a la vez.

## 3. Qué ve y hace el usuario (recorridos)

Cada recorrido, primero en el ordenador y después en el móvil.

### R1 · Explorar sin buscar nada

*Alguien llega desde la portada y no sabe qué quiere ver.*

- **Ordenador:** ve una frase de bienvenida, el cerebro humano y el de rata uno al lado del otro y una lista de regiones ordenada de fuera a dentro (como propone Sofía: primero la superficie, después hipocampo, amígdala…). Gira un cerebro con el ratón, pasa por encima de una zona y ve su nombre; hace clic y se abre a la derecha (o debajo) una **tarjeta corta**: nombre en español, sigla, dos o tres frases de qué hace, y la pareja en el otro cerebro con su grado de equivalencia. En el otro cerebro se ilumina la pareja.
- **Móvil:** ve un cerebro cada vez (ver UX-1), con un interruptor «Humano | Rata» arriba. Gira con un dedo, toca una zona y la tarjeta sube desde abajo, tapando solo la parte de abajo de la pantalla. Un botón de la tarjeta, «Ver en la rata», cambia de cerebro con la pareja ya marcada.

### R2 · Buscar una región concreta

*Un estudiante escribe «hipocampo», «CA1» o «hippocampus».*

- El buscador entiende el nombre en español, en inglés, la sigla y los sinónimos de la tabla de búsqueda que revisa Sofía, sin importar tildes ni mayúsculas.
- Elegir un resultado hace lo mismo que tocar la región: la marca, lleva el corte hasta ella, la hace visible aunque sea interna (ver UX-4) y abre su tarjeta.
- **Móvil:** el buscador está arriba, fijo; la lista de resultados ocupa la pantalla mientras se escribe y desaparece al elegir.

### R3 · Comparar la misma región en rata y humano

*Lo que diferencia a SYNAPTICA.*

- La tarjeta de cada región tiene un apartado **«En el otro cerebro»**: el nombre de la pareja, su grado (**clara**, **parcial** o **discutida**, con palabra e icono, nunca solo con color) y la nota breve de Sofía.
- «Ver lado a lado» abre la vista de comparación: los dos cerebros, cada uno con su región marcada y su corte en ella. En el móvil, uno encima del otro, cada uno con su mitad de pantalla, sin giros automáticos.
- Si la región aún no tiene pareja, la tarjeta lo dice con calma («Todavía no hemos comparado esta región») y no hay botón de comparar. Con la tabla de Sofía, esto debe ser la excepción.

### R4 · Leer la ficha completa de una región

*Alguien quiere saber más.*

- La tarjeta tiene un enlace **«Ficha completa»** que abre una página propia de la región (ver UX-2): descripción, enfermedades relacionadas, últimos estudios **en animales** y **en humanos** por separado y con sus etiquetas (revista o preprint, humanos o animales, retractado o corregido), técnicas con las que se estudia (enlaces a Neuro Lab), y créditos del atlas.
- La ficha se lee sin el 3D: carga rápido, se puede compartir, y funciona en móviles antiguos o sin gráficos 3D.

### R5 · Llegar desde otra sección

*Desde una noticia, una técnica de Neuro Lab o una entrada del glosario.*

- Cada región tiene su dirección propia. Un enlace «Ver en el atlas» abre Neuro Atlas con esa región ya elegida y su tarjeta abierta.
- Al revés, desde la ficha de una región se llega a las noticias, técnicas y entradas del glosario relacionadas.

### R6 · Entender una sigla (petición P6)

- **Ordenador:** al pasar el ratón por una sigla (en la tarjeta, la ficha o la etiqueta del cerebro) sale un recuadro con el nombre completo, la sigla y la definición corta del glosario.
- **Móvil:** no hay «pasar por encima»: un toque en la sigla abre ese mismo recuadro, y otro toque fuera lo cierra.
- Si la sigla todavía no está en el glosario, sale solo el nombre completo.

### R7 · Estudiar con cortes y coordenadas

*Un estudiante quiere ver la región en un corte, con milímetros desde Bregma.*

- En «Más opciones» (ver UX-3) activa el corte 2D, el modo atlas en blanco y negro o la tinción, y despliega las coordenadas en milímetros. Todo como en el prototipo.
- Lo que elija se recuerda la próxima vez en ese navegador.

### R8 · Leer la introducción «humano y rata»

- Un enlace fijo, arriba, «¿En qué se parecen un cerebro humano y uno de rata?», abre una página corta: con pliegues frente a liso, proporciones, qué zonas cambian más. Es texto de la cadena verificada, revisado por Sofía, con alguna imagen del propio visor.

## 4. Estructura de pantallas

```
Neuro Atlas  (/es/atlas/ y /en/atlas/)
├── Portada del atlas
│     frase de bienvenida · enlace a la introducción
│     buscador
│     visor (ordenador: los dos cerebros; móvil: uno, con interruptor)
│     lista de regiones, de la superficie a las internas
│     tarjeta de la región elegida (al lado en ordenador; desde abajo en móvil)
│     una línea de créditos bajo cada cerebro · aviso «no es consejo médico»
├── Introducción: humano y rata
├── Ficha de región, una por región y atlas  (/es/atlas/rata/<sigla>/, /es/atlas/humano/<sigla>/)
│     qué hace · en el otro cerebro (grado y nota) · enfermedades relacionadas
│     estudios en animales · estudios en humanos · técnicas · glosario · créditos
├── Comparación lado a lado  (la portada con las dos regiones elegidas; dirección propia)
└── Créditos y licencias del atlas  (dentro de «Fuentes y licencias» de toda la web)
```

Todas las páginas existen en español y en inglés. El aviso «no es consejo médico» está en todas.

### La tarjeta de una región (lo mínimo)

1. Nombre en español (o inglés) y sigla; el lado (izquierdo, derecho o los dos).
2. Qué hace, en dos o tres frases.
3. En el otro cerebro: pareja, grado y nota, con «Ver lado a lado».
4. «Ficha completa» y, en pequeño, de qué atlas viene.

Lo que hoy enseña el prototipo (códigos internos, etiqueta del mapa) pasa a la ficha completa, plegado en «Datos del atlas».

## 5. Los dos atlas y sus licencias

Los dos cerebros vienen de atlas distintos con licencias distintas:

| Qué | Licencia | Qué permite |
|---|---|---|
| Rata: regiones de Waxholm v4.01 | CC BY 4.0 | Usarlas citando a sus autores |
| Rata: la resonancia de plantilla de Waxholm (no la usamos hoy) | CC BY-SA 4.0 | Lo mismo, y lo que hagamos con ella, con la misma licencia |
| Rata: cortes reales de Nissl (Blixhavn 2023), solo en el corte 2D | CC BY 4.0 | Citando |
| Humano: áreas de Julich-Brain v3.1 | CC BY-NC-SA 4.0 | Solo sin fines comerciales, citando y con la misma licencia |
| Humano: capas debajo (CerebrA, CIT168, sustancia blanca de ICBM) y tinción BigBrain | Cada una la suya ([ADR D3](../adr/0003-visor.md)) | — |

**La regla:** nunca se fabrica un dato nuevo a partir de dos atlas a la vez, porque heredaría la licencia más restrictiva (la no comercial de Julich-Brain). En la práctica:

- **Cada atlas va en su propia carpeta y su propio archivo**, con su licencia al lado. El cerebro humano y el de rata nunca se funden en una sola imagen, malla o volumen.
- **La tabla de parejas rata ↔ humano es nuestra:** solo guarda qué región de un atlas va con cuál del otro (por su código), el grado y la nota de Sofía. No copia formas, posiciones ni medidas de ningún atlas, así que es trabajo propio de SYNAPTICA (CC BY-SA 4.0).
- **Todo lo que se calcula** (el centro de una región, sus contornos, su número de vóxeles) se calcula **dentro de un solo atlas**, y se guarda junto a ese atlas con su licencia.
- **La resonancia de plantilla de Waxholm (CC BY-SA)** no entra mientras no haga falta. Si algún día entra, va en su propio archivo y nunca se mezcla con las regiones de Julich-Brain.
- **En pantalla** los dos cerebros pueden estar juntos (es como poner dos libros uno al lado del otro), pero cada uno lleva **su línea de créditos** debajo («Rata · Waxholm v4.01 · CC BY 4.0 · créditos») y la cita completa está en la página de créditos (ver UX-6).
- **Los textos propios** (qué hace cada región, notas) se escriben desde Wikipedia y los estudios, no desde los atlas, y no incluyen material de los atlas con licencia NC.

## 6. Decisiones de diseño (decididas por Aday el 2026-11-15)

### UX-1 · ¿Cuántos cerebros se ven a la vez?

| Opción | A favor | En contra |
|---|---|---|
| **A.** Los dos siempre, como el prototipo | La comparación siempre a la vista; lo que nos diferencia | En el móvil, uno encima del otro: el de abajo no se ve, y dos visores 3D cuestan el doble de batería y de espera |
| **B.** Uno cada vez (humano por defecto) con interruptor, y la vista «lado a lado» solo al comparar | Pantalla limpia; carga la mitad al entrar | En el ordenador desaprovecha el ancho y esconde lo que nos diferencia |
| **C.** Según la pantalla: los dos en el ordenador; uno con interruptor en el móvil, y «lado a lado» al comparar | Lo mejor de cada una; en el móvil, la comparación sigue a un toque | Dos diseños que mantener y probar |

**Decisión de Aday: C.** En el ordenador hay sitio y la comparación es el gancho; en el móvil, cargar y mover un solo cerebro es lo que hace que responda rápido.

### UX-2 · ¿Dónde vive la información de cada región?

| Opción | A favor | En contra |
|---|---|---|
| **A.** Solo en el panel del visor, como hoy | Una sola pantalla | Sin 3D no hay contenido; no se puede enlazar ni encontrar desde un buscador; un panel largo tapa el cerebro en el móvil |
| **B.** Solo en páginas propias por región; el visor solo navega | Páginas ligeras, accesibles y enlazables | Cada toque saca al usuario del visor |
| **C.** Tarjeta corta en el visor y ficha completa en su página propia | Explorar sin salir y leer a fondo cuando se quiere; las fichas son páginas estáticas como el resto de la web (se generan con `syn site` y pasan `site --check`) | Dos sitios donde mostrar lo mismo (se generan de los mismos datos) |

**Decisión de Aday: C.** Además, las fichas sirven de destino para los enlaces desde Noticias, Neuro Lab y el glosario, y funcionan aunque el 3D falle.

### UX-3 · ¿Cómo se ordenan los controles?

| Opción | A favor | En contra |
|---|---|---|
| **A.** La barra del prototipo, todo a la vista | Nada escondido | 9 botones y 6 barras para quien solo quiere girar el cerebro |
| **B.** A la vista solo el buscador, «Recortar» y «Más opciones»; dentro: vista (solo 3D / 3D + corte), aspecto (color / atlas / tinción dibujada o real), «Aislar» y las coordenadas en mm | Pantalla limpia; todo sigue a un toque; en el móvil cabe en una fila | Hay que descubrir «Más opciones» |
| **C.** Dos modos, «Explorar» y «Estudiar», que cambian los controles visibles | Claro para cada público | Una decisión más al entrar; la frontera entre modos es arbitraria |

**Decisión de Aday: B**, recordando la última elección en el navegador.

### UX-4 · ¿Qué hace el otro cerebro, y cómo se ven las regiones internas?

| Opción | A favor | En contra |
|---|---|---|
| **A.** Como hoy: el otro cerebro gira y mueve su corte hasta la pareja | Se ve la pareja sin hacer nada | Desorienta («se reinicia»); en el móvil puede pasar fuera de la pantalla |
| **B.** El otro cerebro marca la pareja sin moverse; un botón «Ir a la pareja» lo gira y lleva el corte | Nadie pierde lo que estaba mirando | Un toque más |
| **C.** B, y además las regiones internas se ven solas: al elegir una, el resto del cerebro se vuelve translúcido hasta que se suelta la selección | Hipocampo y amígdala visibles sin saber qué es «recortar» | Hay que probar que el visor lo pinta bien y rápido en el móvil antes de prometerlo |

**Decisión de Aday: B ahora, y probar C** en el primer paso de código; si no va fluido en el móvil, se queda B con «Recortar» automático para las internas. Con «movimiento reducido» activado en el sistema, nunca hay giros animados.

> **Ojo: cambia una petición de Sofía.** En S3 pidió que el otro visor gire y lleve su corte hasta la pareja (P3, respuesta Q3). Con B eso pasa al pulsar «Ir a la pareja», no solo. Se le pregunta (pregunta 5) y, si prefiere el giro automático, se vuelve a A, mejor suavizado.

### UX-5 · ¿Cuándo se carga el visor?

| Opción | A favor | En contra |
|---|---|---|
| **A.** Al entrar, como hoy | Sencillo | Unos 19 s de espera en red lenta, sin nada que leer |
| **B.** Primero la página (texto, buscador, lista y una imagen fija de cada cerebro); el visor se carga justo después, solo | Hay algo útil en unos segundos; el visor llega sin pedirlo | La imagen fija es un archivo más por cerebro que generar |
| **C.** El visor solo al pulsar «Ver en 3D» | La carga más ligera | Esconde lo más vistoso de la web, que Sofía quiere como puerta de entrada (propuesta) |

**Decisión de Aday: B.** En el móvil, con UX-1 C, solo se carga el cerebro que se ve; el otro, al cambiar. La tinción real sigue cargándose solo si se pide.

### UX-6 · ¿Cómo se enseñan los créditos y licencias?

| Opción | A favor | En contra |
|---|---|---|
| **A.** Todo bajo cada cerebro, como hoy | Imposible de no ver | Media pantalla de citas |
| **B.** Una línea por cerebro (atlas, versión, licencia, «créditos») y la cita completa en la página de créditos del atlas | Cumple las licencias (autor, licencia, cambios, enlace) sin ocupar sitio | La cita completa queda a un clic |
| **C.** Un botón ⓘ sobre cada cerebro que abre los créditos | Lo más limpio | Las licencias CC piden un crédito razonablemente visible; un icono solo se queda corto |

**Decisión de Aday: B.** Las fichas de región llevan también su línea del atlas de origen.

## 7. Accesibilidad y rendimiento

### Accesibilidad

El 3D no lo puede usar un lector de pantalla ni, bien, un teclado. Por eso **nada importante depende solo del 3D**:

- **Todo se alcanza sin el visor:** la lista de regiones, el buscador y las fichas son HTML normal. Si el navegador no tiene gráficos 3D, la página lo dice y sigue sirviendo.
- **Teclado:** buscador y lista con flechas, Intro y Escape (como el prototipo); foco siempre visible; la tarjeta se cierra con Escape y devuelve el foco donde estaba.
- **Lector de pantalla:** al elegir una región se anuncia («Hipocampo, CA1, izquierdo; pareja en la rata: CA1, grado claro»), con una zona `aria-live`.
- **Color:** el grado de equivalencia y la selección nunca se indican solo con color (palabra, icono o contorno). Contraste mínimo AA en textos y avisos.
- **Tamaños:** objetivos táctiles de al menos 44 × 44 px; los avisos dentro del lienzo nunca bajan de 12 px (hoy llegan a 8 px).
- **Movimiento:** con «reducir movimiento» del sistema, sin giros animados.
- **Idioma:** cada página con su `lang`; los nombres en latín o inglés dentro de una página en español, marcados.
- **Tema oscuro:** el corte de la tinción es un portaobjetos claro; se enmarca para que no deslumbre.

### Rendimiento (medido en S3)

Medidas del prototipo con un móvil simulado (390 × 844, «Slow 4G», CPU ×4, gráficos por software, así que pesimistas), de `spikes/s3/results/measure-*.json`:

| Pieza | Peso (comprimido) |
|---|---|
| Niivue 0.69 (el visor) | 0,80 MB |
| Rata: regiones de Waxholm | 0,55 MB |
| Humano: Julich-Brain | 0,54 MB |
| Humano: CerebrA · CIT168 · sustancia blanca | 0,16 · 0,08 · 0,29 MB |
| Tablas de nombres y código propio | ~0,1 MB |
| **Total al entrar** | **2,49 MB · 19,3 s hasta poder usarlo** |
| Tinción real del humano (BigBrain), solo si se pide | +1,61 MB (unos 9 s más en red lenta) |
| Cortes reales de Nissl de la rata, de uno en uno | ~35 KB por corte (índice de 42 KB) |

- **Fluidez al girar:** 9–10 fotogramas por segundo con el 3D limitado a 1,5× en pantallas táctiles (22 a 1×). En el S23 Ultra de Aday va bien.
- **Modo atlas:** 0,2–0,5 s la primera vez (contornos calculados en el navegador).
- **Sin otros dominios ni seguimiento:** todo sale de la propia web.
- **Sin medir todavía:** cuánto tarda en responder un toque en el móvil. Se mide en el primer paso de código, por partes (leer la región, repintar el cerebro tocado, repintar el otro).

**Objetivos propuestos para la Fase 2** (a confirmar por Aday en el primer paso de código; se miden con el mismo `measure.mjs`):

- texto, buscador y lista utilizables en **menos de 5 s** en el móvil simulado (UX-5 B);
- el primer cerebro del móvil listo en **menos de 12 s** (UX-1 C: un solo atlas y Niivue: unos 1,9 MB con el humano y sus cuatro capas, 1,35 MB con la rata; la sustancia blanca, la capa que más pesa, puede llegar después);
- respuesta a un toque, medida y por debajo de **0,3 s** en el móvil simulado si se puede (pintar primero el cerebro tocado y después el otro);
- ningún atlas por encima de los 3 MB del presupuesto de D3.

## 8. Preguntas para Sofía

Cuantas más respuestas, mejor; ninguna corre prisa antes de que empiece el código.

1. **¿Qué cerebro ve primero alguien que no sabe nada:** el humano, el de rata o los dos?
2. **Orden de las regiones:** propusiste ir de la superficie hacia dentro. ¿Con qué regiones empezamos (una lista corta), y cuáles son de tu investigación para darles prioridad en la tabla de parejas?
3. **Grados de equivalencia:** ¿te bastan tres, «clara», «parcial» y «discutida»? ¿Puedes describir cada uno en una frase para enseñarla en la web?
4. **Nombres en español:** ¿qué fuente prefieres para traducir los nombres de las regiones (la terminología anatómica oficial, el uso de clase, Wikipedia)? ¿Las siglas se dejan como en los atlas (casi todas en inglés)?
5. **Al tocar una región,** ¿prefieres que el otro cerebro gire solo hasta la pareja o que solo la marque y tú decidas si ir?
6. **Lo de estudiante** (corte 2D, modo atlas en blanco y negro, tinción, milímetros desde Bregma): ¿bien dentro de «Más opciones», o hay algo que quieras siempre a la vista?
7. **Introducción humano y rata:** ¿qué diferencias no pueden faltar?
8. **Enfermedades relacionadas** en cada región (salen de Wikidata): ¿quieres revisar la lista de cada región antes de que se publique?
9. **Estudios en animales y en humanos:** ¿cuántos por región (por ejemplo, los 5 más recientes de cada)?
10. **Técnicas por región:** ¿se te ocurren parejas región ↔ técnica que no deberían faltar?
11. **Lo que aún falta en el humano** (la médula, el tronco dividido, el bulbo olfatorio, los tractos): ¿lo decimos en la página, o basta con no enseñarlo?
12. **Tinción dibujada:** la intensidad de cada región la eligió el dibujo (por ejemplo, el hipocampo oscuro y la sustancia blanca pálida). ¿Le echas un vistazo cuando tengamos la versión nueva?

## 9. Lo que viene después de este estudio

Con UX-1–UX-6 decididas, falta que Sofía responda a las preguntas (y confirme UX-4). Entonces: se cierra este documento, se marca la casilla del estudio en `SCOPE.md` y empieza el siguiente paso de Neuro Atlas (pasar `build_assets.py` a `src/synaptica/atlas/` con tests y reescribir el visor en `site/static/`). Las respuestas de Sofía que sean contenido (nombres, grados, orden) van a su cola de revisión, no se publican sin ella.

## Anexo para Aday · de nota de UX a propuesta

| Nota de S3 | Dónde se resuelve |
|---|---|
| Barra de botones y deslizadores enormes | UX-3 |
| «Aislar» no afecta al corte 2D | Al aislar, el corte también atenúa lo demás (sin opción: es un fallo) |
| Nombres solo en inglés; buscador en inglés | Nombres de la tabla revisada por Sofía (pregunta 4); el buscador usa ES, EN, sigla y sinónimos |
| Solo 12 parejas de prueba | Tabla de Sofía; aviso amable si falta (R3) |
| El buscador marca los dos lados y el punto va al izquierdo | Se mantiene, y la tarjeta dice «los dos hemisferios» |
| CA1 invisible en «Solo 3D» | UX-4 |
| Panel que cambia muy deprisa al arrastrar | La tarjeta se actualiza al parar 150 ms, como el resaltado |
| El otro cerebro solo se entera al soltar | Se mantiene (con UX-4 B ni siquiera se mueve) |
| Avisos del lienzo de hasta 8 px | Mínimo 12 px; si no caben, el aviso va bajo el lienzo |
| Tinción real sin indicador de carga | Indicador con el peso («1,6 MB») antes de pedirla |
| Etiqueta flotante solo con clic | Igual con clic, buscador y ejes |
| Tema oscuro y portaobjetos claro | Marco alrededor del corte |
| El otro cerebro gira y parece reiniciarse; en móvil, fuera de la vista | UX-1 y UX-4 |
| El toque tarda en el móvil | Medir por partes; pintar primero el cerebro tocado (apartado 7) |
| Brave en la red local | Solo afecta a las pruebas en casa; publicada funciona |
