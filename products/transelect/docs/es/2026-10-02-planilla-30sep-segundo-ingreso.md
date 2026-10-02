# Planilla del 30-sept-2026: segundo ingreso y columnas renombradas

Documento técnico de referencia (en inglés):
[Source Contract V2](../source-contract-v2.md), sección «Evidence from the
30-Sept-2026 workbook». El contexto de la reunión está en
[Reunión del 02-10-2026](2026-10-02-reunion-cambios-y-preguntas.md).

## Qué cambió en la planilla

En la hoja «Resumen» de `PlanillaMaestra-CD_30sep2026.xlsx`:

- Las columnas **Fecha de ingreso** y **N Ingreso** pasaron a llamarse
  **Fecha de ingreso1** y **N Ingreso1** (columnas Y y Z).
- Aparecen dos columnas nuevas después de «Hoy»: **Fecha de ingreso2** y
  **N Ingreso2** (columnas AC y AD). Están vacías en las 729 filas.
- Por eso «Empresa» se movió de AC a AE y «Sector» de AI a AK.

Con los nombres nuevos, el panel no encontraba «N Ingreso», que es una
columna esencial, y rechazaba la planilla. Ese es el comportamiento previsto
cuando cambia la estructura: se detiene y avisa en vez de leer mal.

## Qué hace ahora el panel

- **Reconoce ambos nombres.** «Fecha de ingreso1» y «N Ingreso1» se leen
  como la fecha y el número de ingreso de siempre. Las planillas anteriores
  siguen importando igual.
- **Lee el segundo ingreso.** «Fecha de ingreso2» y «N Ingreso2» se guardan
  por fila y se muestran en el detalle de cada plan junto al primero. Si la
  planilla publicada no tiene esas columnas, el detalle lo dice en vez de
  mostrar «sin segundo ingreso».
- **No separa celdas con dos valores.** En «Fecha de ingreso1» hay 58
  celdas con dos fechas y en «N Ingreso1» unas 58 con dos números. El panel
  las conserva como texto y las marca; no elige cuál de los dos valores es el
  ingreso y cuál el reingreso. Si esos segundos valores se pasan a las
  columnas «…2», el panel los leerá sin cambios adicionales.
- **La exportación CSV** agrega «Fecha de ingreso2» y «N Ingreso2» a
  continuación de «N Ingreso» (20 columnas en total).

## Qué no cambia

- Ninguna regla de estado, pendientes ni plazos usa todavía el segundo
  ingreso. Eso se definirá con las respuestas de la reunión del 02-10-2026.
- La planilla no se publicó en este cambio. Publicarla sigue siendo una
  decisión explícita de Campo Digital desde «Datos → Importar».

## Preguntas para Campo Digital

1. ¿«Fecha de ingreso2» y «N Ingreso2» corresponden siempre al reingreso
   después de un rechazo?
2. ¿Van a pasar a esas columnas los segundos valores de las 58 celdas que hoy
   traen dos fechas o dos números?
3. ¿Puede un plan tener más de dos ingresos?

Las demás preguntas (ciclo de rechazo, plazo de 90 días hábiles, resoluciones,
Oficina Virtual) están en [la nota de la reunión](2026-10-02-reunion-cambios-y-preguntas.md).
