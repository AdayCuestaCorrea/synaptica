# D2 — Motor común con Paleo Atlas: copiar y adaptar

- **Estado:** aceptada (2026-11-12, inicio de la Fase 1), decidida por Aday
- **Relacionadas:** [SCOPE §8 D2](../../SCOPE.md#8-decisiones) · [Plan de la Fase 1](../fases/plan-fase-1.md) · [D1](0001-almacen.md) · [D4](0004-llm.md)

## Contexto
SYNAPTICA reutiliza el «motor» de Paleo Atlas: cliente HTTP educado, almacén crudo versionado en la rama `data`, dbt sobre DuckDB, la cadena de textos con sus comprobaciones, el sitio estático y el informe de cada ejecución. Los dos repositorios son del mismo autor y los dos tienen el código bajo AGPL-3.0, así que la licencia permite cualquiera de las dos vías. Lo que hay que decidir es cómo se comparte ese código.

Paleo Atlas está en producción y no se toca desde este repositorio (CLAUDE.md). SYNAPTICA está empezando, y su dominio cambia piezas que en Paleo parecían genéricas: fuentes biomédicas, señales de cada estudio (preprint, especie, retractación) y revisión de Sofía.

## Decisión
**Copiar y adaptar.** Cada módulo que viene de Paleo se copia a `src/synaptica/`, se adapta al dominio y dice en su docstring de qué archivo sale. No hay dependencias entre los repositorios. Se valorará extraer un paquete común solo cuando los dos motores estén estables y las piezas copiadas hayan dejado de divergir.

Los textos de contenido de Paleo (fichas, recaps, glosario) no se copian: allí son CC BY-NC-SA y aquí serían CC BY-SA, y copiarlos les quitaría la restricción NC.

## Alternativas consideradas
- **Paquete compartido ya** (por ejemplo `atlas-engine`, instalado desde git en los dos): obliga a modificar Paleo, que está en producción y no se toca desde aquí, para depender de un paquete que todavía no tiene una forma estable. Además, cada cambio de SYNAPTICA arriesgaría romper el pipeline diario de Paleo.
- **Importar Paleo como dependencia:** arrastra su dominio (taxones, PBDB, GBIF) y acopla las versiones de los dos proyectos.
- **Dejar D2 abierta y copiar igualmente:** en la práctica es lo mismo que esta decisión, pero sin dejar escrito el porqué.

## Consecuencias
- **A favor:** cada proyecto evoluciona sin romper el otro; el código copiado se puede leer sin saltar de repositorio; en una entrevista se explica en una frase («duplicación deliberada hasta que la abstracción sea evidente»).
- **En contra:** las correcciones no se propagan solas. Se mitiga con el docstring de origen en cada módulo: un `grep "paleo-atlas"` da la lista de lo que hay que revisar cuando se arregle algo en Paleo.
- **Cuándo revisarla:** al cerrar la Fase 1, comparando los módulos copiados con sus originales. Si siguen casi iguales, se propone el paquete común con un ADR nuevo.

## Pruebas
- Primeros módulos copiados: [`src/synaptica/http.py`](../../src/synaptica/http.py) (desde `paleo/http.py`) y [`src/synaptica/store.py`](../../src/synaptica/store.py) (desde `paleo/store.py`; las fechas pasan a UTC). Sus tests: [`tests/test_http.py`](../../tests/test_http.py) y [`tests/test_store.py`](../../tests/test_store.py), sin red.
- Patrón ya usado en la Fase 0: `src/synaptica/config.py` y `cli.py` adaptados de Paleo; las cadenas de S5 copian `paleo/narrative/checks.py`.
