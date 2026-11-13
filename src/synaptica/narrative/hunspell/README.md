# Diccionario de español para el corrector ortográfico

- `es_ES.aff` y `es_ES.dic`: diccionario RLA-ES v2.9 (español de España) para Hunspell, del proyecto RLA-ES, tomado de github.com/LibreOffice/dictionaries, carpeta `es/`, commit `762abe74008b94b2ff06db6f4024b59a8254c467` (2025-02-13). Sin cambios.
- Licencia: triple y disjunta, GNU GPL v3 o posterior, GNU LGPL v3 o posterior o MPL 1.1 o posterior (ver `LICENSE.md`). SYNAPTICA lo usa bajo la GPL v3 o posterior, compatible con su AGPL.
- `extra_es.txt`: palabras nuestras que el diccionario no trae (términos de neurociencia); se aceptan también su femenino y su plural. Se amplía cuando un término válido bloquee un texto, nunca para dejar pasar una errata.

Lo usa `synaptica/narrative/checks.py` (paso 17 del plan de la Fase 1) a través de `spylls`, Hunspell en Python puro.
