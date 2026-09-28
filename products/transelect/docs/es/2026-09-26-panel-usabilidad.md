# Panel Transelec: mejoras de uso y preguntas pendientes (26-09-2026)

Estas mejoras están en el PR #59. Desde el 28-09-2026 está verificado que funcionan en Railway (ver [estado del piloto](2026-09-28-piloto-en-uso.md)). Esta revisión no publicó ninguna planilla. El registro técnico está en [la bitácora del cambio](../design/2026-09-26-dashboard-usability-pass.md).

## Qué cambia en el panel

- En **Pendientes** y en la cola del **Resumen**, se puede abrir el detalle de un plan directamente desde su fila. Si no hay filtros activos, ya no aparecen botones para quitar filtros que no hacen nada.
- El detalle muestra primero la tramitación y un resumen AEF del plan, con cada valor y la fila de la planilla que lo aporta. Si hay valores contradictorios, los muestra sin elegir uno. Más abajo distingue los datos de la fila seleccionada y permite pasar a otra fila del mismo plan. Una fila sin AEF sigue vacía aunque otra fila del plan lo tenga.
- **Calidad** explica primero qué se encontró, cuántos planes, predios o filas afecta y qué conviene revisar. Quien necesite auditar la cifra puede abrir «Cómo se calcula» y ver las columnas y reglas exactas.
- La tabla por tipo de propietario explica por qué sus estados pueden diferir de los del resumen y presenta ambas cuentas de predios. No se cambió ninguna regla ni se decidió cuál cifra es la oficial.
- La cabecera usa el logo que Campo Digital publica en su sitio web, guardado dentro del panel para que no dependa de cargar ese sitio.

## Preguntas para Campo Digital

1. Para informar el estado de los **predios**, ¿se debe usar «Estado resumido» o la clasificación de la tabla por propietario, que cuenta como «Rechazado» un predio cuando su «Estado» menciona un rechazo?
2. La etapa de pendientes llamada «Rechazado» incluye también ciertos planes sin número de ingreso cuyo estado no habla de preparación ni de un recurso. ¿Ese nombre describe bien esos casos?
3. ¿Qué significa AEF y se registra una vez por plan de manejo o por cada área de corta? La planilla del 09-sept lo trae en la primera fila de 23 planes, pero eso por sí solo no confirma la regla de negocio.
4. Cuando distintas filas de un mismo plan tienen diferente «Estado resumido», ¿cuál corresponde informar?

Hasta recibir esas respuestas, el panel conserva los valores y reglas actuales y muestra cómo llega a cada cifra. La [nota de la planilla del 09-sept](2026-09-26-planilla-09sept-seguimiento-aef.md) conserva las preguntas sobre fechas y columnas.
