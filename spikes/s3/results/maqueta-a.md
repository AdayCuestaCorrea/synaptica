# S3 · Paso 2: maqueta A (siibra-explorer embebido)

Medido el 2026-11-11 con siibra-explorer **v2.14.35** (atlases.ebrains.eu, código Apache-2.0) en Chrome de escritorio. Maqueta en `spikes/s3/a/`:

- `index.html`: dos iframes lado a lado, uno encima del otro por debajo de 800 px;
- `plugin.html`: plugin que reenvía los clics;
- `mobile.html`: la maqueta en un marco de 390 × 844.

Se sirve en local con `python -m http.server 8765 --bind 127.0.0.1 --directory spikes/s3/a`.

## Resultado por requisito

| Qué se mide | Resultado |
|---|---|
| Se deja embeber | **Sí.** `/viewer/` no manda `X-Frame-Options` ni `frame-ancestors` |
| Abrir con una región seleccionada desde la URL | **Sí.** Funciona con `#/a:…/t:…/p:…/rn:<hash>`, donde `rn` es un hash de 32 bits del nombre de la región (`QuickHash` en `src/util/fn.ts`), no su ID. Probado con M1 en la rata y con el área 4a izquierda en el humano |
| Avisar a la página al hacer clic | **Sin API directa.** La API de `postMessage` solo atiende a `window.opener`, es decir, a una pestaña que abrió el visor, no a la página que lo embebe; y además pide permiso con un diálogo. **Hay una vía indirecta:** `?pl=["<url>"]` carga un plugin nuestro, que recibe `sxplr.on.regionsSelected` y puede reenviarlo con `window.top.postMessage`. **No se ha podido probar de extremo a extremo:** Chrome bloquea que una página pública cargue el plugin desde `127.0.0.1` (protección de red local). Hace falta publicarlo en HTTPS (paso 4). Aun funcionando, **cada visita pide confirmar la carga del plugin**, una vez por visor |
| Ventanas al entrar | En cada iframe salen tres: la política de privacidad (Matomo de EBRAINS **activado por defecto**; hay que desmarcarlo a mano), la confirmación del plugin y el tour. La de privacidad no vuelve al recargar; las otras dos sí |
| Seguimiento | En la carga se ven 2 peticiones a `stats.humanbrainproject.eu` (Matomo) **antes** de que el usuario cierre la ventana de privacidad. Son de un tercero: la web tendría que avisar de ello |
| Peso | Código del visor: **6,8 MB** transferidos, los mismos para los dos iframes porque se comparten en la caché del navegador; el más pesado es `vendor.js`, con 1,7 MB. A eso se suman los datos (unas 43 llamadas a `siibra-api` más los bloques de imagen de neuroglancer), que van por un worker y no se han podido pesar desde la página. Es el doble del presupuesto de la maqueta B (unos 3 MB por atlas) antes de cargar ningún dato |
| Móvil (390 px) | El panel lateral del visor ocupa casi todo el ancho; la vista 3D queda en una franja. Las ventanas de inicio tapan la pantalla. No se ha medido la fluidez en un móvil real |
| Dependencia de EBRAINS | Total: el código (atlases.ebrains.eu), los datos (siibra-api y neuroglancer.humanbrainproject.eu) y los términos. Usar ebrains.eu implica aceptar sus *General Terms of Use*, que están en un PDF que no he descargado |
| Autohospedarlo | El frontend se puede compilar como estático, con `SIIBRA_API_ENDPOINTS` y sin `MATOMO_URL`, lo que quitaría el seguimiento. Pero los datos seguirían saliendo de la siibra-api de EBRAINS, y la nuestra exigiría un servidor Python (`siibra-api`), que no cabe en GitHub Pages. Quitar las ventanas o la confirmación del plugin exige mantener un fork de una aplicación Angular |
| Atlas que muestra | Rata: Waxholm **v4** (no v4.01) sobre la RM de plantilla v1.01, que es CC BY-SA 4.0. Humano: Julich-Brain v3.1 sobre MNI152 2009c |

## Lectura

La maqueta A cumple «GitHub Pages sin backend propio», con matices (todo el backend es de EBRAINS), y «los dos atlas a la vez». Pero tiene problemas:

- **regiones clicables por ID:** solo con un plugin que el usuario tiene que aprobar en cada visita y en cada visor;
- **peso en móvil:** 6,8 MB de código antes de los datos, y una interfaz pensada para escritorio;
- un **seguimiento de terceros** activado por defecto.

Queda por medir, al publicar el plugin en HTTPS (paso 4), si el aviso llega de verdad.
