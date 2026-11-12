# S3 · Notas de UX y UI de la maqueta C

Recogidas el 2026-11-11, al terminar las mejoras M1 y M2. **No son un estudio:** el estudio de UX y UI de Neuro Atlas se hace en la Fase 2, antes de construirlo (SCOPE §7), y parte de estas notas. Decisión de Aday: hacerlo ahí, porque es en la Fase 2 donde Neuro Atlas tiene nombres en español, glosario y fichas, y un estudio sobre la maqueta habría que repetirlo.

## Lo que ya hemos visto

- **Controles:**
  - la barra de botones crece con cada paso (vista, recortar, aislar, tres modos y las dos variantes de tinción) y en móvil ocupa varias líneas;
  - los deslizadores de los tres ejes y su nota sobre los mm ocupan mucho bajo cada visor.
- **Aislar selección:** el 3D deja solo la selección, pero el corte 2D sigue mostrando las demás regiones (en todos los modos).
- **Nombres:** solo en inglés, los de cada atlas. En español se avisa en el panel; la traducción, revisada por Sofía, es de la Fase 2. El buscador, por tanto, también busca en inglés.
- **Parejas:** solo hay 3 parejas de prueba, así que casi todo lo que se toca da «sin pareja todavía». En la Fase 2, con la tabla de Sofía, ese aviso será la excepción.
- **Selección por área (buscador):**
  - se resaltan los dos hemisferios, pero el punto va al izquierdo;
  - un área interna, como CA1, no se ve en «Solo 3D» sin recortar, porque la tapa la corteza.
- **Punto de los tres ejes:**
  - al arrastrar, el panel cambia muy deprisa;
  - el otro cerebro solo se entera al soltar (decisión de Aday). Hay que ver si se entiende.
- **Avisos en el lienzo** (tinción): se encogen para caber, hasta 8 px; en un móvil pequeño hay que comprobar que se leen.
- **Peso y espera:**
  - la tinción real del humano tarda unos 9 s más en red lenta, sin indicador de carga;
  - el primer paso al modo Atlas tarda unos 0,4 s en un móvil (cálculo de contornos).
- **Etiqueta flotante:** el nombre junto al punto solo sale al hacer clic, no con el buscador ni con el punto de los ejes.
- **Tema oscuro:** el corte de la tinción es claro (portaobjetos) sobre un fondo oscuro.
- **Móvil (paso 7.9, S23 Ultra):**
  - el otro cerebro gira solo para enseñar la pareja de lado (7.4). Si lo estabas mirando de frente, parece que «se reinicia», y una pareja del hemisferio derecho se ve desde el otro lado;
  - los dos cerebros van uno encima del otro: el que gira puede no estar a la vista;
  - Brave en el móvil no abre direcciones de la red local (probado con Chrome).
  - **al tocar una región aún tarda un poco** (paso 7.10, publicada): un toque lee en profundidad y rehace la tabla de colores de los dos cerebros. En la Fase 2 se puede medir qué parte pesa más (p. ej. pintar primero el cerebro tocado y después el otro).

## Lo que diga Sofía (2026-11-12)

_Pendiente: su revisión de los modos (atlas en blanco y negro, tinción dibujada y real), del buscador y del punto._
