# Transelec — Rediseño de la interfaz (2026-09-13)

Documento de colaboración para Campo Digital y Javier. La versión técnica
completa, en inglés, está en
[el registro de diseño](../design/2026-09-13-frontend-ux-rearchitecture-v1.md).

## Qué se hizo

Se rediseñó la interfaz del tablero Transelec. **No se tocó nada del cálculo**:
ni una regla de estado, ni una fórmula, ni el significado de un campo, ni la
lectura de la planilla, ni las reglas de acceso. Las cifras que aparecen son
exactamente las mismas que antes, calculadas por el mismo servidor, sobre la
misma versión publicada.

Lo que cambió es **dónde está cada cosa y qué tan visible es**.

## Por qué

La versión anterior tenía todas las funciones, pero las tenía todas juntas y
todas con el mismo peso visual. En números medidos sobre la aplicación real:

- la página principal medía 4.210 píxeles de alto en un computador y 7.977 en
  un teléfono;
- once secciones seguidas, siete de ellas con exactamente la misma tarjeta
  blanca, así que la tabla de propietarios, el reporte y el detalle se veían
  iguales entre sí;
- los ocho indicadores tenían el mismo tamaño: «Roles» (un dato de
  referencia) gritaba tan fuerte como «Pendientes prioritarios» (el número que
  significa que alguien tiene trabajo pendiente);
- la tabla de detalle —la herramienta que realmente se usa a diario— era el
  noveno bloque, unos 2.800 píxeles más abajo, debajo de un reporte;
- los botones «Exportar CSV» e «Imprimir» estaban a 2.500 píxeles de la tabla
  que exportan;
- el encabezado ocupaba 200 píxeles antes del primer número, y el 34 % de la
  pantalla en un teléfono.

## Cómo quedó

Cinco secciones, cada una con un trabajo:

| Sección | Responde |
|---|---|
| **Resumen** | ¿Cómo va el programa y qué requiere atención? |
| **Explorador** | Buscar un PMF, rol, N.º de ingreso o predio y ver su detalle |
| **Pendientes** | La cola de trabajo: qué falta presentar y qué fue rechazado |
| **Calidad** | Qué tan confiable es la versión publicada y qué se puede informar |
| **Datos** | Importar planilla y administrar versiones (sólo operador/administrador) |

Los enlaces antiguos `/transelec/importar` y `/transelec/versiones` siguen
funcionando: abren la sección Datos en el panel correspondiente.

### Lo más importante para el uso diario

- **El filtro ahora vive en la dirección web.** Si Javier filtra por empresa o
  escribe un N.º de ingreso, esa vista se puede copiar y enviar por correo, se
  mantiene al recargar la página, y se conserva al cambiar de sección. Antes
  se perdía en cuanto se cambiaba de página.
- **La tabla de detalle es su propia pantalla** (Explorador), con la búsqueda
  arriba de todo y los botones de exportar e imprimir junto a la tabla.
- **Al hacer clic en una fila se abre su detalle completo**, con todos los
  campos de esa fila y las demás áreas de corta del mismo PMF. Esto antes no
  existía: la relación entre PMF, predio, rol y fila de origen no se podía ver
  en ninguna parte.
- **El paso a paso de importación es un paso a paso de verdad**, con el estado
  de cada etapa visible, y el historial de versiones es una línea de tiempo con
  la versión activa arriba.

### Los dos gráficos circulares

Se reemplazaron por barras horizontales. La razón no es estética: los dos
círculos comparaban 68,75 % y 67,92 %, es decir, menos de dos puntos de
diferencia. Medir ese ángulo a ojo es más difícil que leer el número que ya
estaba escrito al lado. Las barras ponen los dos niveles (predios y PMF) sobre
la misma línea de base, que es lo que permite compararlos. **Todos los valores
que mostraban los círculos y el bloque «Estado resumido» siguen estando**, con
su conteo escrito al lado de cada color.

### Lo que se dejó igual a propósito

- Las tres reglas de estado que no coinciden entre sí siguen sin unificarse, y
  siguen mostrando su identificador en pantalla (`estado_resumido_first_row`,
  `pending_priority_legacy`, `owner_stage_legacy`). Esa decisión sigue
  pendiente de Javier.
- Las dos columnas «Carpeta» se siguen mostrando por separado.
- El significado exacto de la columna «90 días» sigue sin interpretarse.
- Las marcas de Campo Digital y Transelec siguen siendo texto, no logotipos:
  no hay autorización sobre esos archivos.

## Qué se le pide a Javier

Nada nuevo respecto de lo ya preguntado. Las preguntas abiertas siguen siendo
las de
[Hallazgos y preguntas para Javier](2026-09-02-hallazgos-y-preguntas-javier.md).

Lo que sí conviene es que Javier **vea la nueva versión y diga si el orden de
las secciones coincide con su forma de trabajar**: en particular, si el
Resumen muestra primero lo que él necesita ver primero, y si la cola de
trabajo de Pendientes está ordenada de forma útil.

## Estado

La versión anterior sigue disponible sin cambios en la rama
`feat/transelec-hosted-pilot-v2`. El rediseño está en
`feat/transelec-ux-rearchitecture-v1`.
