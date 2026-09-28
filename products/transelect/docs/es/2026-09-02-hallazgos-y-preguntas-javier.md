# Transelec — Hallazgos y preguntas para Javier (2026-09-02)

## Qué se hizo

Se revisaron a fondo los dos tableros HTML que Javier usa hoy
(`Dashboard_Transelec_14Ago2026_v0.html` y su versión "Actualizable"), la
planilla maestra (`PlanillaMaestra-CD_14Ago2026.xlsx`) y el estado actual del
código en el repositorio. El objetivo fue asegurar que la próxima versión del
tablero incluya **todas** las funciones útiles que Javier ya usa — no una
versión "inspirada" que descarte cosas sin decírselo. Esta etapa es solo de
levantamiento y diseño: **no se implementó nada nuevo todavía**.

## Qué encontramos

- Los dos tableros de Javier funcionan bien y sin errores técnicos. El
  tablero "Actualizable" agrega, sobre el `v0`, la posibilidad de cargar una
  planilla más reciente directamente en el navegador — pero esa carga vive
  solo en la memoria del navegador: si se cierra o recarga la página, se
  pierde, y no queda ningún registro de quién actualizó qué ni cuándo.
- Encontramos un error concreto en ambos archivos: el filtro "¿Qué ingresos
  superaron 90 días?" usa una fecha fija (26 de agosto de 2026) grabada
  dentro del archivo. Ya no avanza — literalmente no puede saber qué día es
  hoy. Este es el único error que se puede corregir sin pedirle nada a
  Javier; todo lo demás abajo sí necesita su confirmación.
- Encontramos que el mismo PMF puede aparecer con un estado distinto según
  qué parte del tablero se mire (por ejemplo, en la tabla "Estado por tipo
  de propietario" puede figurar como "Rechazado" mientras en los indicadores
  principales figura "En trámite"). No es un error de cálculo: son dos
  reglas distintas conviviendo en el mismo archivo, sin que ninguna esté
  documentada como la oficial.
- La planilla tiene dos columnas que se llaman igual ("Carpeta"), con datos
  distintos. Ambos tableros HTML sólo logran mostrar una de las dos — la
  otra se pierde silenciosamente cada vez que se genera o actualiza el
  archivo.

## Qué NO se inventó

Por política del proyecto, no se inventa una regla de negocio para resolver
una ambigüedad. Cuando el archivo no dice con certeza qué significa algo (por
ejemplo, la columna "90 días", o cuál de las dos "Carpeta" es la oficial), se
deja constancia de la pregunta en vez de adivinar una respuesta.

## Preguntas para Javier

1. Cuando un mismo PMF o predio tiene registros con estados distintos,
   ¿cuál debería ser el estado "oficial" que se muestra? Hoy cada sección
   del tablero decide esto de forma distinta y a veces se contradicen entre
   sí.
2. La planilla tiene dos columnas "Carpeta" con contenido diferente. ¿Cuál
   debería mostrarse, o deberían mostrarse ambas con nombres distintos?
3. ¿Qué representa exactamente la columna "90 días"? No corresponde a
   "Fecha de ingreso + 90 días" en los casos revisados.
4. Al exportar a CSV, ¿qué columnas son realmente útiles para compartir?
   (el archivo `v0` exporta una columna que "Actualizable" no exporta, y
   viceversa).
5. La pregunta "¿Cómo avanza cada empresa?" hoy sólo enfoca un filtro — no
   existe una vista comparativa por empresa. ¿Es una función real que falta,
   o basta con el filtro actual?
6. Los logos de Campo Digital y Transelec están incrustados en los archivos
   HTML actuales. Antes de reutilizarlos en el tablero nuevo, necesitamos
   confirmación de que está autorizado.

## Qué sigue

Con esta base, el siguiente paso es construir el tablero nuevo sobre la
plataforma compartida de Campo Digital: carga autorizada de la planilla,
validación estricta, guardado privado, y publicación explícita de cada nueva
versión — de modo que el tablero deje de depender de archivos HTML sueltos y
pase a mostrar siempre la versión oficial vigente, con historial y
posibilidad de volver a una versión anterior si algo sale mal.

**Importante sobre el acceso**: por ahora no existe una forma de que Javier
ni ningún otro usuario de Campo Digital inicie sesión de forma segura en un
sitio público — el mecanismo de identidad definitivo (a través de una cuenta
Microsoft/Entra de Campo Digital) todavía no está creado. Hasta que eso
exista, los datos reales de Transelec no se publicarán en ningún ambiente
público, ni siquiera de prueba.

## Documentación técnica relacionada

- [Matriz de paridad funcional (inglés, TR-FUNC-*)](../audit/2026-09-02-functional-parity-matrix-v1.md)
- [Auditoría forense de las fuentes (inglés)](../audit/2026-09-02-source-forensic-audit-v1.md)
- [Contrato de la fuente V1](../source-contract-v1.md)
