# D5: Flujo de revisión de Sofía

- **Estado:** aceptada (2026-11-12, Fase 0, spike S4): opción C, decidida por Aday tras la prueba con Sofía
- **Relacionadas:** [SCOPE §8 D5](../../SCOPE.md#8-decisiones) · [plan de S4](../../spikes/s4/PLAN.md) · [resultados](../../spikes/s4/results/README.md) · [guion de la prueba](../../spikes/s4/prueba/GUION.md) · [D4](0004-llm.md) (los textos que revisa)

## Contexto

Sofía, doctoranda en neurociencia, revisa el contenido de SYNAPTICA. Los requisitos de D5:
- sin terminal, sin git y sin editar YAML;
- menos de 1 hora al día;
- cubrir todo lo que revisa:
  - fichas de Neuro Diseases, obligatorias;
  - textos y resúmenes;
  - glosario;
  - términos de búsqueda;
  - temas de noticias;
  - Clásicos de la semana;
  - grado y nota de cada pareja rata ↔ humano.

Hay que saber, además, quién aprobó qué versión y cuándo. Una ficha de Neuro Diseases solo se publica con su aprobación registrada.

Restricciones comunes:
- 0 €;
- repositorio público;
- todo en GitHub Actions y Pages;
- Sofía no es colaboradora del repositorio (D9).

## Decisión

**Página de revisión generada cada día y envío como Issue de GitHub (opción C).**

1. **La página.** El pipeline genera la página con la cola del día, ordenada por prioridad. Ella decide en la página, y las respuestas se guardan en su navegador, así que puede dejarlo a medias.
2. **El envío.** «Enviar» abre el formulario de Issue ya relleno, con un bloque de texto legible. Si el bloque no cabe en una URL (6000 caracteres; medido: GitHub falla hacia 6950 sin sesión), se reparte en varias partes.
3. **La recepción.** Un workflow `on: issues` hace esto:
   - solo lee los Issues de su cuenta (una *variable* del repositorio, no un secreto);
   - toma `reviewed_by` y `reviewed_at` del propio Issue, no de lo que diga el texto;
   - valida cada decisión contra la cola que mostró la página;
   - añade las decisiones a un registro de solo añadir (`review/decisions.jsonl`) en la rama `data`;
   - responde en el Issue y lo cierra.
4. **Cada aprobación se ata a una versión.** Lleva la huella (`content_sha256`) de lo que ella vio. Si el borrador cambia, la aprobación caduca y el elemento vuelve a su cola.
5. **Sus correcciones pasan otra vez las comprobaciones mecánicas:** cifras y nombres, 8 palabras copiadas de la fuente, y frases nuevas sin fuente. El juez LLM solo deja un aviso.
   - Si una comprobación falla, la corrección no se aplica y vuelve a su cola con el aviso.
   - Ella la corrige o elige «Lo mantengo» con un motivo, que queda registrado.
   - Si solo corrige el español, la cadena del LLM rehace el inglés y lo comprueba.
6. **Lo privado no va en la página pública.** Las fichas de Neuro Diseases van en un archivo aparte que Aday le manda. En el Issue solo viaja su decisión y, si corrige, su texto.
7. **Lo público.** Las decisiones y las notas son públicas, y la página lo avisa. Lo privado va por WhatsApp o correo.

## Alternativas consideradas

- **A · Editar en github.com:** exige git y YAML, y que sea colaboradora. Incumple los requisitos.
- **B · Solo el formulario de Issues:** un Issue por elemento. Elegir Clásicos o poner grados resulta incómodo, y no ve el texto como quedará.
- **D · Google Sheets:** era la reserva si C fallaba en la prueba. Supone sincronizar en dos sentidos, otra plataforma y no ver los textos largos como quedarán. Sofía dijo expresamente que prefiere C.
- **E · CMS (Decap) o un Worker:** más servicios, autenticación propia y un secreto en un proxy OAuth.
- **También descartados:**
  - copiar y mandar las decisiones a mano: no escala, y `reviewed_by` saldría de Aday;
  - un token pegado en la página: es gestión técnica para Sofía;
  - el correo: leerlo desde Actions pide un token OAuth.

## Prueba con Sofía (2026-11-12)

Tres rondas reales con su cuenta (`sofiagarciamartinez02`), Issues #2–#10. Ella usó la página sin terminal ni git; los Issues se procesaron a mano con el mismo código que usará el workflow.

| Criterio del guion | Resultado |
|---|---|
| Como mucho una ayuda | Ninguna anotada |
| Ronda 1 en 25 min o menos | **No: 38 min**, pero hizo bastante más de lo pedido (reescribió un resumen entero y propuso 17 siglas en vez de una) |
| Todos sus Issues se leen bien | Sí. Lo que no se aplicó fue por fallos nuestros, ya corregidos |
| Al iniciar sesión en GitHub, el formulario sigue relleno | Sí: el primer envío lo hizo sin sesión iniciada |
| Cuenta de GitHub y decisiones públicas | Le parecen bien si eso ayuda a que profesores y profesionales valoren la web, y prefiere esto a una hoja de cálculo |

Sus respuestas a las preguntas finales:
- **Lo que más le cuesta:** comprobar que los resúmenes dicen la verdad.
- **Volumen:** puede con 40 elementos al día, y con 10 los fines de semana.
- **Lo que echa en falta:** más laboratorio y menos resúmenes y siglas en las próximas fases.

**Fallos que la prueba destapó y se corrigieron, con test.** Ninguno lo había visto el ensayo en seco.
1. La recepción no cargaba el abstract de las fuentes. Sin él no corría la comprobación de copia y las cifras de la fuente salían como nuevas. Ahora, si falta, el Issue espera.
2. La primera palabra de cada párrafo se tomaba por un nombre propio.
3. En «Proponer una sigla» no se veían las siglas que ya existían, y propuso 4 repetidas.
4. Dos rondas con el mismo nombre de archivo: abrió la vieja y reenvió todo. Ahora cada página lleva su ronda en el nombre, en la cabecera y en lo que guarda el navegador. Además, la recepción no apunta dos veces una decisión idéntica.
5. Con un envío en 4 partes perdió la cuenta de cuáles había mandado. Ahora cada envío lleva un identificador y la respuesta dice qué partes faltan.
6. Los Issues de una ronda se comprobaban contra la cola del primer día. Una corrección retenida vuelve como otra versión, así que se rechazaba. Ahora se comprueban contra la cola que mostró su página.

## Consecuencias

- **A favor:**
  - cumple los requisitos y a ella le gusta;
  - cada decisión tiene autor, fecha y versión autenticados por GitHub, sin secretos;
  - el historial completo (grados incluidos) vive en git;
  - la regla de Neuro Diseases se cumple sola, porque la aprobación caduca si cambia el texto;
  - las decisiones públicas muestran que hay revisión humana real.
- **En contra:**
  - **Todo es público** salvo la ficha privada. La página lo avisa y lo privado va por otro canal.
  - **Una corrección larga puede no caber en la URL.** Esa parte se copia y ella la pega a mano. No pasó en la prueba.
  - **Sofía prefiere sugerir a reescribir.** En la ronda 2 detectó una exageración del resumen («es seguro durante el embarazo»), pero dejó el texto igual y escribió su alternativa en la nota. Con este diseño, un «Lo mantengo» habría publicado la exageración. **Mitigación prevista (Fase 1):** si el texto no cambia y la nota trae una frase alternativa, la cadena la aplica, pasa las comprobaciones y se la devuelve para aprobar. Mientras tanto, Aday mira las notas.
  - **Comprobar los resúmenes es lo más costoso.** Mejora posible: mostrar cada frase junto a la cita del estudio que la respalda, que `syn facts` ya genera.
  - **Ampliación de la regla de CLAUDE.md**, que hasta ahora solo hablaba de textos generados: las correcciones de Sofía también pasan las comprobaciones mecánicas.

## Lo que falta para ponerlo en marcha (Fase 1)

- Mover `spikes/s4/review-intake.yml` a `.github/workflows/` y crear la variable `REVIEWER_LOGIN`. Son ajustes de GitHub: necesitan la confirmación de Aday.
- Pasar el código de `spikes/s4/` al paquete (`src/synaptica/review/`).
- Que el pipeline diario genere la cola y la página (en Pages, en una ruta a la que nada enlaza y con `noindex`) y guarde la cola mostrada para la recepción.

## Pruebas

- **Código:** [`spikes/s4/`](../../spikes/s4/):
  - `models.py`, `review_page.py` y `review/template.html`: la cola, la página y el envío;
  - `issue_block.py`: el formato del bloque de texto del Issue;
  - `intake.py`: la recepción;
  - `apply.py` y `ronda.py`: aplicar las decisiones y generar la ronda siguiente;
  - `review-intake.yml`: el borrador del workflow.
- **Tests:** `uv run --group spike-s4 pytest spikes/s4/tests` (111, sin red), con el Issue real #1 como fixture.
- **Datos de la prueba:** `spikes/s4/prueba/datos/`, el registro de sus 3 rondas, que no está en la rama `data`. Sus grados, sus definiciones del glosario y sus siglas se reutilizarán solo si ella los confirma.
- **Resultados y registro:** [`spikes/s4/results/README.md`](../../spikes/s4/results/README.md) y SCOPE v26–v33, v52 y v84–v88.
