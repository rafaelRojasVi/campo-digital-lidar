# Transelec — «¿Cuál es el estado de los planes de manejo?» (2026-09-15)

Documento de colaboración para Campo Digital, Javier y Marianne. La versión
técnica completa, en inglés, está en
[el registro de diseño](../design/2026-09-15-workflow-refinement-marianne-evidence-v1.md).

## De dónde viene este cambio

Marianne explicó cómo se produce hoy el resumen de Power BI: la planilla es la
plantilla, y la pregunta que Javier hace siempre es **«¿cuál es el estado de los
planes de manejo?»**. Ella la responde con la columna `Estado resumido`.

El tablero anterior tenía esa información, pero no la ponía primero: empezaba
con un **porcentaje** de avance, y el número de planes quedaba abajo, entre
datos de referencia. Había que reconstruir la respuesta en vez de leerla.

## Qué se cambió

La primera sección del Resumen ahora es **«Estado de los planes de manejo»**:

- el total de PMF del alcance seleccionado;
- las cifras de `Aprobado`, `En trámite`, `Tachado` (y `Pendiente`, cuando
  existe), contadas **por plan**, no por fila;
- cada cifra dice de qué población es parte («108 de 159 PMF») y **se puede
  hacer clic** para ver esos planes en el Explorador, respetando los filtros que
  ya estaban puestos;
- debajo, el detalle de tramitación (evaluación, rechazos, recursos) como
  desglose, no como un segundo titular;
- debajo, la comparación entre **Campo digital** y **Ecores** en una sola tabla
  con fila TOTAL, en vez de dos bloques repetidos.

Sobre la versión del 14 de agosto, esto da:

| Estado | PMF |
|---|---|
| Aprobado | 108 |
| En trámite | 48 |
| Tachado | 2 |
| Pendiente | 1 |
| **Total** | **159** |

Y por empresa: Campo digital 135, Ecores 24. Los subtotales suman el total.

## Por qué los números del resumen de Power BI no cuadran

El resumen del 29 de julio informa 101 aprobados + 56 en trámite + 3 tachados
frente a un total de 159. Esas cifras suman **160**.

La causa está en la planilla: un PMF aparece con **dos `Estado resumido`
distintos**. En el resumen de julio es `MP015`; en la planilla del 14 de agosto
el que tiene dos valores es **`MP022`** (`En tramite` en casi todas sus filas y
`Tachado` en la fila 307, con `Estado` = `Rechazado` en todas).

El tablero **no reproduce esa suma**. Cada PMF se cuenta **una sola vez**, con
el valor de su primera fila de origen, que es la regla que la aplicación ya
usaba para todo lo demás. Pero tampoco esconde el problema: la sección
**Calidad** muestra todos los PMF con más de un `Estado resumido`, con los dos
valores, cuál se aplicó y de qué fila salió, y el Resumen lo avisa junto al
encabezado.

**Falta que Javier confirme qué estado corresponde a ese PMF.**

## Reforestación: lo que sí y lo que no se puede responder

Marianne pidió dos cifras. La planilla responde una a medias y la otra no.

**«¿Cuántos predios de reforestación son?»** — Se muestran **32 etiquetas
distintas de `Predio Ref`** (de 33, excluyendo el literal `Sin reforestacion`,
que significa ausencia de reforestación y no es un predio).

Se dice «etiquetas» y no «predios» a propósito, porque `Predio Ref` es texto
libre, no un identificador:

- seis etiquetas nombran más de un predio a la vez
  (`Ref036_ Reyes y Ref037_ Reyes`, `Rubi + Marin`, `Ref. 2_Toro + Ref. 35 Barria`,
  `Helga + Niklitschek + Alcaino + Marin`, `Rubi + Narwrath`,
  `Werner + Mavelasqquez`);
- hay casos como `Ref003 Ref004_ Nawrath` que también son dos, sin separador;
- el mismo apellido aparece con distintas escrituras
  (`Ref036_ Reyes`, `Ref 037_Reyes`, `Ref037_ Reyes`).

Así que 32 es una **cota**, no el número real de predios.

**«¿Cuántos propietarios de reforestación son?»** — **No se muestra ninguna
cifra**, porque la planilla no tiene un campo de propietario. La única columna
relacionada es `Tipo de propietario`, que es una categoría de tenencia
(`Servidumbre firmada`, `Poseedor`, `BNUP`, variantes de concesión) compartida
por cientos de filas: dice *bajo qué figura* se usa el terreno, no *quién* es el
dueño. Los apellidos que aparecen dentro de `Predio Ref` son texto libre y no
identifican a una persona de forma confiable.

El tablero muestra «No disponible en el origen», **no un cero**: un cero se
leería como «no hay propietarios», que sería falso.

### Qué haría falta en el origen

Para responder ambas preguntas con certeza, la planilla necesitaría cuatro cosas:

| Campo | Para qué |
|---|---|
| `id_predio_reforestacion` | Identificar cada predio de reforestación sin depender del texto |
| `id_propietario_reforestacion` | Identificar a cada propietario |
| `nombre_propietario_reforestacion` | Mostrar su nombre |
| una asociación entre ambos | Permitir más de un propietario por predio |

No se agregó nada a la base de datos por esto: son campos que todavía no existen
y no se inventa estructura para datos que no hay.

## La captura de WhatsApp (65 planes)

Esa captura informa Pendientes 27, No ingreso 3, Desistida 1, Recurso 16,
Rechazos 18, total 65.

**Esas categorías no se pueden reproducir** con `Estado resumido` ni con
`Estado` ni con ninguna combinación de columnas de la planilla entregada. Falta
una regla, un filtro o una versión distinta de los datos.

No se inventó ninguna regla para que el tablero mostrara 65. Queda pendiente.

## Preguntas para Campo Digital

1. ¿Qué columnas y reglas producen `Pendientes`, `No ingreso`, `Desistida`,
   `Recurso` y `Rechazos`?
2. ¿El total de 65 es de todas las empresas, solo Campo Digital, solo planes no
   aprobados, u otro filtro?
3. ¿Qué identifica de forma única un predio de reforestación: `Predio Ref`,
   `Rol Ref`, la combinación de ambos, o un identificador que falta?
4. ¿Un predio de reforestación puede tener más de un propietario?
5. ¿Qué campo identifica al propietario?
6. ¿Qué `Estado resumido` corresponde al PMF que aparece con dos valores
   (`MP015` en julio, `MP022` en agosto)?

## Qué no se tocó

El inicio de sesión, los permisos por rol, la carga y validación de planillas,
la publicación de versiones, el historial, la exportación a CSV y la navegación
de cinco secciones siguen exactamente igual.

## Documentación relacionada

[Registro de diseño (inglés)](../design/2026-09-15-workflow-refinement-marianne-evidence-v1.md) ·
[Rediseño de la interfaz](2026-09-13-rediseno-interfaz-transelec.md) ·
[Hallazgos y preguntas para Javier](2026-09-02-hallazgos-y-preguntas-javier.md)
