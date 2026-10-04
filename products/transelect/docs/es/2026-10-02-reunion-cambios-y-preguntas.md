# Reunión del 02-10-2026: cambios pedidos, orden propuesto y preguntas

Esta nota resume lo conversado el 02-10-2026 sobre el panel Transelec, lo que
se verificó en el código y en la planilla del 30 de septiembre, el orden en
que proponemos hacer los cambios y las preguntas que necesitamos responder
antes de programar. Nada de esto está implementado todavía. El registro
técnico en inglés está en
[Transelec post-launch backlog V1](../design/2026-10-02-post-launch-backlog-v1.md).

## 1. La planilla del 30 de septiembre no se puede publicar todavía

Revisamos `PlanillaMaestra-CD_30sep2026.xlsx` con el mismo reconocedor que usa
el panel al importar (solo lectura; la planilla no se copió al repositorio ni
se publicó).

- Las columnas `Fecha de ingreso` y `N Ingreso` ahora se llaman
  **`Fecha de ingreso1`** y **`N Ingreso1`**, y aparecen dos columnas nuevas,
  **`Fecha de ingreso2`** y **`N Ingreso2`**, vacías en las 729 filas.
- El panel reconoce las columnas por su nombre exacto. Con el nombre nuevo no
  encuentra `N Ingreso`, que es una columna esencial, y rechaza la
  importación. Es el comportamiento previsto cuando cambia la estructura:
  se detiene y avisa en vez de leer mal.
- El primer cambio del plan (que el panel reconozca los nombres nuevos y lea
  el segundo ingreso) ya está programado y probado; falta publicarlo en el
  servidor. Detalle en
  [la nota de la planilla del 30-sept](2026-10-02-planilla-30sep-segundo-ingreso.md).
- **Ojo:** el 02-10-2026 a las 12:37 (hora de Chile) Javier publicó en el
  panel una planilla también llamada «30 Sept» (729 filas, 6 advertencias
  reconocidas). El panel publicado la aceptó, así que esa copia conserva los
  nombres antiguos `Fecha de ingreso` y `N Ingreso`. La copia que recibimos
  por correo, con los nombres `…1` y las columnas `…2`, es otra revisión.
  Necesitamos saber cuál es la vigente (pregunta 11).

También contamos lo que hay en esas columnas, sin mirar valores de negocio:

- `Fecha de ingreso1`: 602 fechas, 64 fechas escritas en texto (el panel ya
  las lee), **58 celdas con dos fechas** y 2 celdas con `-`.
- `90 dias`: 58 celdas con dos fechas.
- `N Ingreso1`: 562 números con forma `n/n-n/n`, 101 números sin esa forma y
  **unas 58 celdas con dos números**.

Las 58 celdas dobles coinciden entre las tres columnas. Nuestra lectura es que
son el ingreso y el reingreso escritos en una misma celda. El panel no separa
celdas dobles ni elige una de las dos fechas; esas filas quedan sin fecha y
se muestran tal como vienen. **Si esos valores se pasan a las columnas
`…2`, el panel los leerá sin cambios adicionales.**

## 2. Qué se pidió y qué significa para el panel

1. **Un rechazo no es un final.** `Rechazado` significa que CONAF pide un
   documento nuevo; todo rechazo termina en `Aprobado` o `Desistido`. Hoy el
   panel solo detecta la palabra «rechaz» en el `Estado` y no conoce
   `Desistido`. Las columnas `Tipo de rechazo` y `Reingreso_Tec`,
   `Reingreso_Legal`, `Reingreso_RecRep` se importan pero no se interpretan.
   Propuesta: un estado de ciclo por plan (sin ingreso, ingresado, rechazado
   a la espera de reingreso con su tipo, reingresado, aprobado, desistido).
   Lo que no calce en esas categorías se mostrará como «sin clasificar», no
   se adivina.
2. **Reingresos.** La planilla ya trae el segundo ingreso (`…2`). El panel
   lo mostrará junto al primero en el detalle de cada plan.
3. **La pestaña «Pendientes» pasa a llamarse «Estado»** y mostrará ese ciclo
   por plan. Las reglas actuales siguen disponibles en «Cómo se calcula».
4. **90 días hábiles.** El panel calculará el plazo de CONAF sumando 90 días
   hábiles (lunes a viernes, sin feriados nacionales de Chile) a la fecha de
   ingreso más reciente, y lo comparará con la columna `90 dias` de la
   planilla para ver si coinciden. Hoy solo compara esa columna con la fecha
   actual.
5. **Enlace a la Oficina Virtual de CONAF** desde cada plan, una vez
   confirmada la dirección del portal.
6. **Fechas y números de ingreso sin formato.** El panel conserva el texto
   original y marca lo que no pudo leer. Pedimos usar las columnas `…2` en
   vez de dos valores en una celda, y una sola forma de escribir el número.
7. **Editar en el panel y descargar la planilla con marca «web».** Quien
   edite un valor en el panel podrá descargar la planilla con la misma
   estructura, con las celdas editadas marcadas como «web» y el resto
   intacto; al subir una planilla nueva, el panel avisará si un valor
   editado difiere del de la planilla. Es el cambio más grande: el panel hoy
   no permite editar nada por diseño, así que requiere un diseño propio
   antes de programar.

## 3. Orden propuesto

| Orden | Cambio | Por qué en este lugar |
|---|---|---|
| 1 | Reconocer `Fecha de ingreso1/2` y `N Ingreso1/2` | Sin esto, la planilla actual no se publica y nada de lo demás ve el reingreso. |
| 2 | Pestaña «Estado» con el ciclo del plan (rechazo, reingreso, desistido) y el enlace a la Oficina Virtual | Depende del punto 1 y de las respuestas de la sección 4. |
| 3 | Plazo de 90 días hábiles | Depende del punto 1 y de saber qué fecha inicia el plazo. |
| 4 | Edición en el panel y descarga con marca «web» | Cambia cómo funciona el panel; se diseña aparte después de los anteriores. |

## 4. Preguntas para Campo Digital

1. ¿Confirman el ciclo «Rechazado → reingreso → Aprobado o Desistido»? ¿Dónde
   se anota hoy `Desistido`: en `Estado resumido`, en `Estado` o en ninguno?
2. ¿Qué valores toma `Tipo de rechazo` y cómo se relacionan con
   `Reingreso_Tec`, `Reingreso_Legal` y `Reingreso_RecRep`? ¿Son marcas 0/1?
3. ¿`Fecha de ingreso2` y `N Ingreso2` son siempre el reingreso después de un
   rechazo? ¿Van a pasar las 58 celdas con dos valores a esas columnas?
4. ¿Puede un plan tener más de dos ingresos?
5. ¿El plazo de 90 días hábiles vuelve a empezar con el reingreso? ¿Cuál es
   la fecha base: `Fecha de ingreso1` o `Fecha de ingreso2`?
6. ¿Qué contiene hoy la columna `90 dias`? ¿Prefieren que el panel la
   calcule?
7. Cuando un plan tiene dos resoluciones, ¿cuál es la vigente? ¿La planilla
   va a traer número y fecha de resolución?
8. ¿Cuál es la dirección exacta de la Oficina Virtual de CONAF y se puede
   abrir un expediente por su número de ingreso?
9. Para la edición en el panel: ¿qué campos se pueden editar, quién puede
   hacerlo y la marca «web» va por fila o por celda en la planilla
   descargada?
10. Para `N Ingreso`: 101 celdas son números sueltos y 562 tienen la forma
    `n/n-n/n`. ¿Hay un formato oficial (oficina/número-año)?
11. Hay dos planillas «30 Sept»: la que Javier publicó el 02-10-2026 (nombres
    antiguos de columnas) y la que recibimos con `Fecha de ingreso1/2` y
    `N Ingreso1/2`. ¿Cuál es la vigente, y la planilla maestra seguirá con
    los nombres nuevos?

Hasta recibir estas respuestas, el panel conserva las reglas actuales y
muestra cómo llega a cada cifra. Las preguntas anteriores sobre AEF, celdas con
dos fechas y fechas con solo mes siguen abiertas en
[la nota de la planilla del 09-sept](2026-09-26-planilla-09sept-seguimiento-aef.md)
y en [la nota de usabilidad](2026-09-26-panel-usabilidad.md).

## 5. Actualización del 04-10-2026: decisiones y preguntas nuevas

Rafael respondió parte de las preguntas a partir de sus notas de la reunión.
Los diseños técnicos (en inglés) están en
[Estado](../../../../docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md),
[90 días hábiles](../../../../docs/superpowers/specs/2026-10-04-transelec-plazo-90-habiles-design.md)
y [edición en el panel y descarga con marca «web»](../../../../docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md).
Todavía no hay nada programado.

Decidido:

- **Ciclo (pregunta 1).** Un rechazo no es un final; termina en aprobado o
  desistido. La planilla no usa «Desistido» sino «Descartado». El panel
  muestra la palabra de la planilla y trata ambas como cierre (pregunta 12).
- **Inicio del plazo (pregunta 5).** Los 90 días hábiles se cuentan desde el
  ingreso más reciente: `Fecha de ingreso2` si existe, si no
  `Fecha de ingreso1`.
- **Días hábiles.** Lunes a viernes, sin feriados nacionales de Chile.
- **Edición en el panel (pregunta 9).**
  - *Campos:* se pueden editar `Estado`, `Estado resumido`,
    `Tipo de rechazo`, los tres `Reingreso_*`, las fechas y números de
    ingreso 1 y 2, y `90 dias`.
  - *Quién:* editan operadores y administradores.
  - *Marca «web»:* va por celda, con color de fondo y una nota de Excel que
    dice quién, cuándo y el valor anterior. El resto de la planilla queda
    igual.
  - *Planilla nueva distinta:* si una planilla nueva trae otro valor en una
    celda editada, manda la planilla y el panel lo avisa en Calidad.
- **Oficina Virtual (pregunta 8, en parte).** La consulta de CONAF es un
  formulario con el campo «N.º de solicitud». No existe un enlace directo
  por número, así que el panel abrirá la página y permitirá copiar el número.

Siguen abiertas las preguntas 2 a 4, 6, 7, 10 y 11. En la pregunta 2, además
de 0 y 1 aparece el valor 2.

Preguntas nuevas:

12. ¿«Descartado» y «Desistido» son lo mismo?
13. ¿El «N.º de solicitud» de la Oficina Virtual es el `N Ingreso` de la
    planilla?
14. Hay filas con `Estado resumido` «Aprobado» y `Estado` «Recurso
    reposición» sin resultado. ¿El recurso sigue pendiente o el `Estado`
    está desactualizado?
15. ¿El plazo de 90 días empieza el día hábil siguiente al ingreso? ¿Se
    suspende mientras se responden observaciones?
16. ¿Un recurso de reposición o jerárquico reinicia los 90 días, o solo un
    nuevo ingreso?
17. ¿Cuentan los feriados regionales?
