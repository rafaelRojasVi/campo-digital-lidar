# Panel Transelec: el piloto está en uso (28-09-2026)

## Qué está funcionando

- El panel está publicado en Railway con el inicio de sesión de Google Workspace (`@campodigital.cl`), las mejoras de uso del PR #59 y el refuerzo de seguridad del PR #60.
- El 26-09-2026 una persona de Campo Digital inició sesión y cargó, validó y publicó una planilla. Después de eso, el resumen y los pendientes respondieron sin errores.
- El panel ya no publica la documentación técnica de la API (`/docs`, `/openapi.json`). Solo la necesita el equipo de desarrollo, y fuera de producción sigue disponible.

## Qué falta confirmar

1. **Respaldos.** Los datos del panel están en la base de datos y el volumen de Railway. Falta confirmar en Railway que haya respaldos automáticos de ambos.
2. **Administración.** Javier debe tener el rol de administrador y otorgar ese mismo rol a la cuenta de Rafael, para que la gestión de accesos no dependa de una sola persona.
3. **Preguntas sobre la planilla.** Siguen abiertas las preguntas sobre el significado de AEF, las celdas con dos fechas y las fechas que solo indican el mes. Están en [la nota de la planilla del 09-sept](2026-09-26-planilla-09sept-seguimiento-aef.md) y en [la nota de usabilidad](2026-09-26-panel-usabilidad.md). Hasta tener respuesta, el panel muestra esos valores tal como vienen y no elige entre ellos.

## Próximo paso técnico

La versión publicada vive en una rama de trabajo. Se integrará a la rama principal del repositorio para que la próxima publicación salga de una base única.
