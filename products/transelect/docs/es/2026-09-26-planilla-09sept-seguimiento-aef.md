# Planilla del 09-sept-2026: seguimiento AEF y revisión de columnas

Documento técnico de referencia (en inglés):
[Source Contract V2](../source-contract-v2.md).

## Qué cambió en la planilla

La hoja «Resumen» de `PlanillaMaestra-CD_09Sept26.xlsx` agregó cinco columnas
al inicio (A–E): **AEF**, **Quien solicita**, **Fecha solicitud**,
**Fecha corta** y **Fecha termino**. Las 30 columnas de siempre se movieron
cinco posiciones a la derecha (ahora F–AI), la columna vacía de separación
pasó de AE a AJ, y desde AK hay tablas resumen/dinámicas propias de la hoja.

La plataforma anterior exigía cada columna en una posición fija, por lo que
rechazaba esta planilla aunque el cambio fuera razonable.

## Qué hace ahora la plataforma

- **Reconoce las columnas por su encabezado**, no por su posición. Tolera
  columnas insertadas, reordenadas o adicionales, y el separador en otra
  posición. Las tablas resumen a la derecha del separador no se leen.
- **Las dos columnas «Carpeta»** se distinguen por sus vecinas: la que está
  junto a «PMF» es la carpeta del PMF; la que está entre «Tramite» y
  «Sector» es la carpeta normalizada. Si una se mueve y ya no se puede
  distinguir, la importación se detiene y pide revisión (o se puede renombrar
  como «Carpeta origen» / «Carpeta normalizada»).
- **Antes de publicar se muestra una revisión**: qué columnas se reconocieron,
  qué se ignoró y qué requiere atención, siempre con fila y columna.
- **Nunca se adivina un dato**: no se «rellena hacia abajo» y no se corrigen
  fechas. Una fecha escrita como texto se lee solo si es inequívoca (una sola
  fecha con el mes en palabras, p. ej. «13 de noviembre de 2024»); en todos
  los demás casos queda sin fecha. En ambos casos se conserva el texto
  original de la celda y se muestra.
- Los problemas graves (falta una columna esencial, una columna ambigua, dos
  columnas con el mismo nombre y valores distintos) **bloquean** la
  importación. Los demás son **advertencias**: la versión se importa, pero
  para publicarla hay que confirmar que se revisaron. Publicar sigue siendo un
  paso explícito y auditado.

## Resultado con la planilla del 09-sept

- Se importan 729 filas con PMF, 159 PMF, 272 identificadores prediales y
  164,63 ha, igual que antes. Las 30 columnas de siempre se leen con los
  mismos valores que con el método anterior.
- AEF, Fecha corta y Fecha termino tienen dato en 23 filas; Quién solicita y
  Fecha solicitud, en 19.
- Advertencias:
  - fila 315: «Fecha corta» anterior a «Fecha solicitud»;
  - fila 375: «Fecha termino» anterior a «Fecha corta»;
  - «Fecha de ingreso» tiene 124 celdas y «90 dias» 63 celdas escritas como
    texto (187 en total), que antes quedaban vacías sin aviso:
    - 67 son una sola fecha escrita en palabras (64 y 3): **se leen como
      fecha** y se conserva el texto;
    - 116 tienen **dos fechas en la misma celda** (58 y 58): no se elige
      ninguna, la fila queda sin fecha y se muestra el texto;
    - 4 tienen solo «-» (2 y 2): quedan sin fecha.

    La revisión antes de publicar lista **todas** las filas afectadas.
- Ningún PMF tiene valores distintos de AEF, solicitante o fechas entre sus
  filas.

## Cómo se ve en el panel

- Nueva sección **Seguimiento AEF**, **por PMF**: AEF, solicitante y fechas
  de cada PMF, indicando la fila de la planilla de la que viene cada valor,
  y las fechas a revisar. Debajo se mantiene el detalle por fila.
- Si en una planilla futura dos filas de un mismo PMF traen valores
  distintos (por ejemplo, dos AEF diferentes), **no se elige ninguno**: se
  marca como conflicto, se muestran ambos valores con sus filas y la
  publicación requiere confirmar la revisión.
- Las filas no se modifican: una fila sin AEF sigue **vacía** en el
  Explorador y en el detalle de la fila, que indica en qué fila del PMF está
  el seguimiento.
- En el **Explorador**, una columna AEF y dos filtros nuevos (AEF y Quién
  solicita), que funcionan por fila.
- La exportación CSV nombra las dos carpetas «Carpeta PMF» y «Carpeta
  normalizada» (antes «col. E» / «col. AC», letras que cambiaron con esta
  planilla). En «Fecha de ingreso», si la celda tenía texto que no se pudo
  leer como fecha, se exporta ese texto en vez de dejarla vacía.

## Preguntas para Campo Digital

1. ¿Qué significa AEF y qué significa cada valor («Presentado»,
   «Solicitado, se puede cortar»)?
2. En los 23 casos, el AEF está en la **primera fila** de su PMF y las demás
   filas del PMF están vacías. Por eso ahora lo mostramos por PMF. ¿Pueden
   confirmar que el AEF se registra una vez por PMF (y aplica a todas sus
   áreas de corta) y no por cada área de corta?
3. Todas las «Fecha termino» son el día 1 del mes. ¿Indican solo el mes? Si es
   así, la fila 375 podría no ser un error.
4. ¿Las filas 315 y 375 tienen fechas mal ingresadas?
5. ¿Se pueden ingresar como fecha de Excel las celdas de «Fecha de ingreso» y
   «90 dias» que hoy están escritas como texto?
6. En las 116 celdas con dos fechas, ¿qué significa cada una y cuál es la que
   corresponde a la columna?
