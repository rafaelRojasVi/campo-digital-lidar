# Preguntas para Javier — Gestión Predial Forestal (Degenfeld)

Fecha: 2026-08-29

Revisamos a fondo la base entregada (`001_DEGENFELD_2026.zip`, capa
`Gdb_Degenfeld2026_mv`: 1.568 polígonos, 13 predios, 10.422,61 ha, con el
dashboard HTML existente). Estas preguntas son lo que la propia base **no**
puede responder y que necesitamos para construir sobre seguro.

## 1. Base vigente e historial

1. ¿`Gdb_Degenfeld2026_mv` es la base vigente y única del patrimonio? ¿El
   sufijo `_mv` significa algo (¿iniciales de quien editó?)?
2. El historial interno muestra actualizaciones 2012, 2017, 2018, 2022,
   2023, 2024 y 2026. ¿Conservas esas bases anteriores y quieres que el
   sistema guarde ese historial, o solo importa el estado 2024/2026?
3. Cuando actualices de nuevo (¿2028?), ¿nos entregarías un nuevo shapefile
   completo como este, o editarías directo en una base compartida?

## 2. Unidad de trabajo e identificadores

4. ¿Cuál es tu unidad principal de trabajo: el predio, el rodal, o el
   polígono de uso? (En la base, un "rodal" puede tener varios polígonos.)
5. El número de rodal (`N_Rodal`) viene vacío en 143 polígonos y repetido en
   otros (p. ej. rodal 856 de Hacienda Trinidad aparece 3 veces; Lumaco
   tiene 7 polígonos con rodal 0). ¿Cómo identificas tú un rodal en terreno
   y en informes? ¿Los vacíos son áreas sin rodal asignado?
6. Encontramos 2 posibles errores de asignación: un polígono llamado
   `Purretrun` con código `PU2` (0,34 ha) y uno llamado
   `Cancha Larga_HJ1_LT1` con código `FLM` (0,03 ha). ¿Cuál es el dato
   correcto? ¿Y qué distingue `Purretrun` (PU1) de `Purretrun2` (PU2)?

## 3. Códigos de uso

7. ¿Confirmas la lectura de los códigos tipo `Pi06`, `En11`, `Eg03`, `Po99`:
   especie + año de plantación (Pi = P. radiata, En = E. nitens,
   Eg = E. globulus, Po = P. oregon)? ¿Qué significan los sufijos `Rn` y
   `Rzg`, los códigos con `??` (p. ej. `Pi?? Rzg`), y los compuestos como
   `Po99Eg97`?
8. En la columna de código 2026 hay 8 valores cortados por ancho de campo
   (quedaron como `RaCoRo01P*`). ¿Cuál debería ser el valor completo?
9. ¿El campo `Editada` (valores `si`, `mv`, vacío) marca qué exactamente:
   ediciones de atributos, de geometría, o de una campaña específica?

## 4. Flujo de trabajo real

10. La base viene de ArcGIS según su historial interno, pero el producto se
    llama "Gestión Predial / QGIS". ¿Con qué programa editas hoy y con cuál
    quieres seguir editando?
11. Sobre las *solicitudes de planes de manejo* que describes en tu nota:
    ¿quién las crea, qué información mínima llevan (¿rodal, superficie,
    especie, año?), quién las aprueba, y qué pasa después con la base?
12. ¿Qué consulta necesitas responder más rápido en el día a día? (p. ej.
    "¿cuántas hectáreas de P. radiata por plantar/cosechar tiene HT?")
13. ¿Qué deberían poder **editar** los usuarios y qué solo **ver**? ¿Los
    dueños en Alemania solo visualizan? ¿Necesitan la interfaz en otro
    idioma?

## 5. Calidad de datos (para tu confirmación, no urgente)

14. Hay 7 polígonos con geometría auto-intersectada y un par de micro-
    polígonos duplicados (0,16 m² en Purretrun). ¿Los corregimos nosotros y
    te avisamos, o prefieres corregirlos tú en la base original?
