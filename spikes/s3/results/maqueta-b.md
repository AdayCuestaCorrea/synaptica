# S3 · Pasos 4 y 6: maqueta B (three.js con mallas propias)

Medido el 2026-11-11. Maqueta en `spikes/s3/site/b/`; datos del paso 3 en `spikes/s3/site/data/`; three.js 0.187.0 y el decodificador Draco guardados en `spikes/s3/site/vendor/three-0.187.0/` (MIT y Apache-2.0, ver `SOURCE.md`).

Se sirve en local con `python -m http.server 8766 --bind 127.0.0.1 --directory spikes/s3/site`, y en el móvil se ve en `mobile.html?m=b` (un marco de 390 × 844).

## Qué hace

- Dos lienzos, rata (Waxholm v4.01) y humano (Julich-Brain v3.1), lado a lado; por debajo de 800 px, uno encima del otro.
- Cada atlas es un glTF con Draco: el contorno del cerebro, transparente, y las regiones de prueba, una malla por región y lado.
- **Clic o toque** en una región: el panel muestra el nombre, el lado y el ID (`408` en la rata; `JULICH_BRAIN_…_AREA_4A_PRECG_LEFT` y la etiqueta del mapa en el humano). En el otro atlas se resaltan las regiones equivalentes **del mismo lado**, con «grado: pendiente de Sofía», y las demás se atenúan.
- **Estructuras internas:** se ven a través del contorno transparente. Hay botones para ocultar el contorno y para «Aislar selección», que deja solo la región y su equivalente.
- Licencia, cita y fuente de cada atlas bajo su lienzo; aviso «no es consejo médico» arriba. Español e inglés (`?lang=en`).
- Se dibuja solo cuando algo se mueve, para no gastar batería en reposo.

## Mediciones

Con `spikes/s3/measure.mjs` (Brave 1.99 / Chromium 157 sin interfaz, por el protocolo de DevTools). Cada ejecución usa un perfil limpio, sin caché, en un móvil emulado (390 × 844, DPR 3, táctil) con la red «Slow 4G» de DevTools (1,6 Mbps, 562,5 ms de RTT) y la CPU ×4. Son 3 ejecuciones; las cifras apenas varían entre ellas. Datos completos en `measure-b.json` y `measure-b-gzip.json`.

| | Sin comprimir (`http.server`) | Con gzip en el texto, como GitHub Pages (`serve-gzip.mjs`) |
|---|---|---|
| Peso transferido | 3,21 MB · 20 peticiones | **1,07 MB** · 20 peticiones |
| Hasta poder usar los dos visores | 22,0 s | **10,1 s** |

- **Reparto del peso, con gzip:** el código ocupa unos 0,69 MB, de los que three.js son 0,43 MB (`three.core.js` y `three.module.js` sin minificar; el paquete 0.187.0 no trae versión minificada). Los datos de los dos atlas ocupan unos 0,37 MB: los glTF, 168 y 181 KB, y las tablas de nombres.
- **Fluidez al girar:** 20 fps con la CPU ×4 y 23 fps sin limitar, con los dos visores girando a la vez. Ojo: sin interfaz, el navegador dibuja WebGL **por software** (SwiftShader), así que es una cota pesimista. En el Chrome de escritorio no he podido medirlo bien, porque el navegador automatizado limita los fotogramas (2–40 por segundo según el foco); dibujar un fotograma cuesta 0,03–0,06 ms de CPU por visor. **Falta probarlo en un móvil real.**
- **Táctil:** en las 3 ejecuciones, un toque selecciona M1 izquierda y en el humano se resaltan Area 4a y 4p izquierdas; arrastrar con un dedo gira la vista y pellizcar la acerca.
- **Otros dominios:** ninguno. Todas las peticiones van a `127.0.0.1`. Las 4 URL `blob:` las crea la propia página para el decodificador Draco y no salen a la red. La única petición fallida era `favicon.ico`, ya quitada con un icono vacío.

## Lectura

- Cumple los requisitos duros de D3: GitHub Pages sin servidor propio, regiones clicables por ID, licencias separadas por atlas, los dos atlas a la vez, y 1,07 MB en total (el presupuesto era de unos 3 MB por atlas).
- **Lo que pesa es three.js, no los datos.** Empaquetarlo solo con lo que se usa (con esbuild, por ejemplo) lo dejaría en una fracción. Además, una lista de `modulepreload` evitaría la cascada de importaciones, que con 562 ms de RTT cuesta varios segundos. No se ha hecho: sería un paso de compilación nuevo y lo tendría que decidir Aday.
- **Limitación de contenido:** solo se pueden clicar las regiones que tienen malla, que ahora son las de prueba. Cada región nueva es una malla nueva, de unos 5–10 KB comprimida.
- **Asimetrías:** Julich-Brain tiene áreas de tamaño muy distinto en cada hemisferio, como la 4a (ver `README.md`, paso 3). Se ve en la maqueta y viene así en los datos originales.
