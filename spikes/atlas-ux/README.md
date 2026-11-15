# Neuro Atlas · maquetas del estudio de UX (Fase 2)

Pantallas estáticas para enseñar a Sofía las decisiones UX-1–UX-6 del [estudio de UX](../../docs/fases/fase-2-atlas-ux.md) (SCOPE v157). **No son el visor ni la web:** los cerebros son capturas fijas del prototipo de S3 y los botones solo cambian de pantalla. Solo en español: es material de trabajo para Sofía, no una página de la web.

Se ven en local con:

```sh
python -m http.server 8767 --bind 127.0.0.1 --directory spikes/atlas-ux
# http://127.0.0.1:8767/  (#s1 … #s9 abre cada pantalla)
```

## Qué hay

- `index.html`: 9 pantallas (5 de ordenador, 3 de móvil y los créditos), cada una con una nota de qué cambia respecto al prototipo y qué se le pregunta a Sofía. Colores del estilo «Noche» de la web (`site/static/noche.css`).
- `img/`: 6 capturas del prototipo de S3, **una por atlas** (nunca los dos cerebros en un mismo archivo):

  | Archivo | Atlas | Licencia |
  |---|---|---|
  | `rata-3d.webp`, `rata-hipocampo-3d.webp`, `rata-hipocampo-corte.webp` | Waxholm v4.01 (Kleven et al. 2023) | CC BY 4.0 |
  | `humano-3d.webp`, `humano-hipocampo-3d.webp`, `humano-hipocampo-corte.webp` | Julich-Brain v3.1 + CerebrA + CIT168 + sustancia blanca ICBM 2009c | CC BY-NC-SA 4.0 (la más estricta de sus capas; detalle en el [ADR D3](../../docs/adr/0003-visor.md)) |

  Cambios: colores de la paleta propia de SYNAPTICA, fondo del atlas de la web, recorte de márgenes.
- `capture.mjs`: genera las capturas con el navegador sin interfaz, contra el prototipo servido en local (mismo cliente que `spikes/s3/measure.mjs`).

## Cómo se regeneran las imágenes

```sh
python -m http.server 8766 --bind 127.0.0.1 --directory spikes/s3/site &   # anota el PID y ciérralo con kill <PID>
node spikes/atlas-ux/capture.mjs
cd spikes/atlas-ux/img
for f in rata-3d humano-3d rata-hipocampo-3d humano-hipocampo-3d; do
  magick $f.webp -fuzz 4% -trim +repage -bordercolor '#101a33' -border 60 -quality 86 $f.webp; done
for f in rata-hipocampo-corte humano-hipocampo-corte; do
  magick $f.webp -gravity south -crop 100%x52%+0+0 +repage -fuzz 4% -trim +repage \
    -bordercolor '#101a33' -border 30 -quality 86 $f.webp; done
```

## Lo que no es dato

Todo lo que va en un recuadro amarillo de borde discontinuo es un **hueco**: contenido que aún no existe (descripciones verificadas, notas de Sofía, estudios, enfermedades). Lo marcado «ejemplo» (el grado «parcial», el orden de las regiones, las técnicas) enseña el formato y no es una afirmación. El nombre «Formación hipocampal» lleva el aviso de que la traducción la revisa Sofía.
