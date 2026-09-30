# Rodales: cargar, revisar y publicar versiones

Fecha: 2026-09-30. Estado: **listo para revisión, no publicado en la
plataforma**. Nada cambió todavía en el Rodales que ven los usuarios.

## Qué cambia para ustedes

Hasta ahora, poner una nueva capa de rodales en la plataforma requería que
Rafael la importara a mano. Con esta entrega, un **operador o administrador
de Rodales** puede hacerlo desde el propio panel:

1. **Cargar versión.** Se sube el shapefile como un archivo `.zip` (con
   `.shp`, `.shx`, `.dbf`, `.prj` y `.cpg`). La plataforma revisa el archivo
   y la capa. Si algo no corresponde, lo dice en palabras simples (por
   ejemplo, "Falta el archivo .prj" o "el sistema de coordenadas no es
   WGS 84 / UTM 18S") y no guarda nada.
2. **Revisión.** La versión queda **pendiente de revisión**. El mapa que ven
   los demás **no cambia**. En la revisión se ve: qué archivo es, quién lo
   subió y cuándo, cuántos polígonos y hectáreas tiene, el sistema de
   coordenadas, las geometrías con problemas y qué cambió respecto de la
   versión publicada. También se puede abrir en el mapa, solo para quien
   revisa.
3. **Publicar.** Solo cuando alguien selecciona «Publicar» (y lo confirma),
   todos los usuarios pasan a ver la nueva versión. Queda registrado quién lo
   hizo y cuándo.
4. **Versiones.** Se ve la lista de todas las versiones, su origen, quién las
   cargó y el historial de publicaciones. Cualquier versión publicada antes
   se puede **restaurar**, también con confirmación y registro.

Los usuarios con acceso de solo lectura ven el mapa publicado y el historial,
pero no las versiones pendientes.

## Cómo se comparan dos versiones

La plataforma compara los polígonos **solo por su geometría**. El OBJECTID y
el número de rodal no sirven para saber si un polígono es "el mismo" entre
una exportación y otra (en la base actual hay 143 rodales en blanco y pares
predio/rodal repetidos), así que se muestran solo como referencia.

- Si un polígono tiene exactamente la misma geometría, se considera el
  mismo y se listan los atributos que cambiaron.
- Si la forma cambió, o un polígono se superpone con varios, la plataforma
  lo marca como **para revisar**. No decide si fue un redibujo, una división
  o una unión.
- **Nunca** concluye que un rodal fue cortado porque su forma o sus
  atributos cambiaron. Un cambio es solo un cambio.

Si la versión tiene geometrías inválidas (la base actual tiene 7) o cambios
para revisar, para publicarla hay que marcar que se revisaron.

## Lo que probamos

Todo el recorrido (cargar, revisar, publicar, ver, restaurar), los permisos,
archivos dañados o incompletos y la recarga directa de cada página, con datos
de prueba. También cargamos en privado, en un entorno local, el archivo real
`001_DEGENFELD_2026.zip`: fue aceptado con sus 1.568 polígonos, 10.422,61 ha
y 7 geometrías inválidas, tal como las conocíamos. Ese archivo no se subió a
ningún repositorio ni a la plataforma.

## Qué no incluye (a propósito)

**Los cortes todavía no se registran.** Antes de construirlo necesitamos las
respuestas de la sección 6 de las
[preguntas para Javier](preguntas-campo-digital.md): corte total o parcial,
fechas, respaldo, aprobación y cómo se asocia un corte a un rodal cuando
llega un shapefile nuevo.

## Qué necesitamos de Campo Digital

1. Las respuestas sobre cortes (sección 6 de las preguntas).
2. Quién será el primer administrador de Rodales (pendiente desde la entrega
   anterior).

## Documentación relacionada

[Detalle técnico (inglés)](../upload-review-publish-v1.md) ·
[Rodales en línea](rodales-en-linea.md) ·
[Preguntas para Campo Digital](preguntas-campo-digital.md)
