# Decisiones de arquitectura (ADR)

Un **ADR** (*Architecture Decision Record*) es una página corta que guarda **una** decisión de arquitectura:
- el problema que había;
- qué se decidió;
- qué alternativas se descartaron y por qué;
- qué cuesta la decisión.

Sirve para que dentro de un año (o en una entrevista) se pueda explicar el porqué sin depender de la memoria.

Las decisiones son las D1–D9 de [`SCOPE.md` §8](../../SCOPE.md#8-decisiones). Si un ADR contradice a `SCOPE.md`, manda `SCOPE.md`. Cuando una decisión se matiza más tarde, se añade una sección «Revisión» con la fecha; no se reescribe la historia.

Nombre de archivo: `000N-titulo-corto.md`, donde N es el número de la decisión (D1 → `0001-…`).

| ADR | Decisión | Estado |
|---|---|---|
| — | Todavía no hay ninguno: D1, D3, D4 y D5 se cierran en la Fase 0 con los spikes S2–S4 | — |

Restricciones comunes a todas:
- **0 €** al mes;
- **repositorio público**;
- dos personas: Aday desarrolla y Sofía revisa el contenido sin terminal ni git;
- una web estática en GitHub Pages que se actualiza sola cada día.

## Plantilla

```markdown
# DN — Título de la decisión

- **Estado:** propuesta | aceptada (AAAA-MM-DD, Fase N) | revisada (AAAA-MM-DD) | sustituida por DM
- **Relacionadas:** [DM](000M-….md) · [SCOPE §8](../../SCOPE.md#8-decisiones)

## Contexto
Qué problema hay, qué restricciones aplican y qué se midió o probó (spike).

## Decisión
Qué se hace, en una o dos frases, y lo que implica.

## Alternativas consideradas
- **Opción A:** por qué no.
- **Opción B:** por qué no.

## Consecuencias
- **A favor:** …
- **En contra:** … y cómo se mitiga.

## Pruebas
Enlaces al código, a los tests, al spike y a las cifras reales que la sostienen.
```
