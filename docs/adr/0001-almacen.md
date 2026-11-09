# D1 — Almacén: DuckDB, BigQuery sandbox o ambos

- **Estado:** propuesta (2026-11-09, Fase 0, spike S2). **Pendiente de la decisión de Aday.**
- **Relacionadas:** [SCOPE §8 D1](../../SCOPE.md#8-decisiones) · ADR D2 y D3 de Paleo Atlas (DuckDB; el estado vive en git y el almacén se reconstruye entero)

## Contexto
El motor de Paleo Atlas reconstruye cada día el almacén entero a partir del crudo versionado en git. Así cualquier día es reproducible y el estado no depende de una base de datos. En Paleo el almacén es DuckDB. Para el CV de Aday interesaba un almacén en la nube, y BigQuery tiene un *sandbox* sin tarjeta. La recomendación inicial de `SCOPE.md` era BigQuery, si S2 confirmaba que funciona desde Actions.

## Qué midió S2
Workflow [`spike-s2.yml`](../../.github/workflows/spike-s2.yml), [ejecución 42708935204](https://github.com/AdayCuestaCorrea/synaptica/actions/runs/42708935204) del 2026-11-09. El mismo proyecto dbt ([`spikes/s2/dbt/`](../../spikes/s2/dbt/)) se ejecutó en los dos motores: un seed con 10 artículos de PubMed, una vista, una tabla y 8 tests.

| | BigQuery sandbox (EU) | DuckDB |
|---|---|---|
| Acceso desde Actions | **Funciona sin tarjeta y sin clave guardada**, con Workload Identity Federation limitada a este repositorio. Se configuró sin activar la facturación | Local, sin red |
| `dbt build` (11 nodos) | **22,7 s** según dbt; 30 s el paso entero | **0,37 s** según dbt; 4 s el paso entero |
| Seed (load job) | Funciona | Funciona |
| Modelo incremental (MERGE) | **Falla** en la segunda ejecución: *«DML queries are not allowed in the free tier»* | Funciona |
| Caducidad | **60 días** por defecto en el dataset, incluidas las vistas | No caduca |

Límites documentados del sandbox ([documentación oficial](https://docs.cloud.google.com/bigquery/docs/sandbox), consultada el 2026-11-09): 1 TiB de consultas al mes, sin DML, sin streaming, sin Data Transfer Service y, sobre todo:

> «You are granted a **lifetime limit of 10 GiB of storage**. This quota is **not refunded upon data deletion**.»

## El problema
El patrón del motor, reconstruir todo cada día, **gasta el cupo de por vida en cada ejecución**. Como referencia, el almacén de Paleo ocupa 83 MiB en DuckDB, comprimido; BigQuery cuenta bytes lógicos sin comprimir, así que en BigQuery ocuparía más. Reconstruirlo a diario agotaría los 10 GiB en **menos de unos 120 días**, y SYNAPTICA crecerá con unos 500–800 artículos de PubMed al día. Cuando el cupo se agota, el sandbox deja de admitir datos y la única salida es activar la facturación, que nuestra regla de 0 € prohíbe.

No he podido medir el consumo real del cupo: la API no lo expone, y la cifra de 120 días es una estimación a partir del tamaño de Paleo, no una medida.

## Opciones

### A. BigQuery como almacén principal, reconstruido cada día
- **A favor:** es lo que más suma al CV (GCP y dbt-bigquery en producción).
- **En contra:** el cupo de por vida se agota en meses; no hay incrementales (sin DML) para gastar menos; la ejecución es unas 60 veces más lenta en este proyecto pequeño; y no se puede trabajar en local sin instalar `gcloud`.
- **Veredicto:** inviable a medio plazo con la regla de 0 €.

### B. DuckDB, como Paleo
- **A favor:** probado, rápido, sin red ni cupos; CI y local idénticos.
- **En contra:** no añade nada nuevo al CV.

### C. DuckDB como almacén principal y BigQuery como espejo de los marts publicados (recomendada)
- El pipeline diario sigue siendo el de Paleo, sobre DuckDB.
- Una vez por semana, Actions sube a BigQuery **solo las tablas finales** (marts) con load jobs, que el sandbox sí admite, usando la misma autenticación sin clave de S2. Allí quedan para consultas y análisis, por ejemplo un panel en Looker Studio, que es gratuito.
- **Consumo estimado:** el tamaño de los marts por 52 semanas al año. Con marts de 10–20 MiB serían 0,5–1 GiB al año, de 10 a 20 años de cupo. Es una estimación: hay que medirla con los marts reales de la Fase 1.
- **A favor:** el CV incluye BigQuery, Workload Identity Federation y carga desde Actions, sin poner en riesgo el pipeline. Si el sandbox cambia o se agota, la web no se entera.
- **En contra:** un paso y una pieza más que mantener, y BigQuery no es el almacén de trabajo (hay que contarlo con honestidad en el README y en la entrevista).

### D. BigQuery solo con vistas sobre el crudo
- **Idea:** el crudo se carga con load jobs y todos los modelos son vistas, que no ocupan almacenamiento.
- **En contra:** las tablas de crudo caducan a los 60 días y hay que recargarlas enteras, así que el cupo también se gasta, aunque más despacio. Además, cada consulta y cada test recalcula desde el crudo, y todo dbt queda limitado a vistas. Es mucha complejidad para esquivar un límite.

## Consecuencias si se elige C
- dbt mantiene un solo proyecto con dos *targets*. Los modelos que se suben a BigQuery tienen que ser SQL portable; se usan las macros multi-base de dbt, como `dbt.type_string()` en S2.
- Ni modelos incrementales ni snapshots de dbt, que en BigQuery usarían MERGE. No afecta, porque el almacén se reconstruye entero (como en Paleo).
- Lo que falta medir en la Fase 1: el tamaño real de los marts y su consumo semanal en BigQuery.

## Pruebas
- Ejecución: https://github.com/AdayCuestaCorrea/synaptica/actions/runs/42708935204. La primera ejecución falló con `iam.serviceAccounts.getAccessToken denied` porque el permiso de IAM aún no se había propagado; la repetición, minutos después, pasó.
- Proyecto dbt: [`spikes/s2/dbt/`](../../spikes/s2/dbt/). Inspección de la caducidad: [`spikes/s2/inspect_bq.py`](../../spikes/s2/inspect_bq.py).
- Configuración de GCP: proyecto `synaptica-514221` sin facturación; cuenta de servicio `synaptica-ci` con `bigquery.dataEditor` y `bigquery.jobUser`; pool `github` con la condición `assertion.repository=='AdayCuestaCorrea/synaptica'`.
