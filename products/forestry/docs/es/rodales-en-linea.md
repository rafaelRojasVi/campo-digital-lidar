# Rodales en la plataforma Campo Digital

Fecha: 2026-09-29. Estado: **preparado, todavía no publicado.**

## Qué cambia

El visor del Patrimonio Degenfeld (Rodales) queda listo para abrirse desde
la misma plataforma que Transelec: se inicia sesión una vez con la cuenta
de Google de Campo Digital y se elige el proyecto.

- **Solo quien tenga acceso a Rodales lo ve.** Iniciar sesión no basta: la
  cuenta debe tener un permiso de Rodales. Quien solo tiene Transelec no ve
  la tarjeta de Rodales y, si abre la dirección directamente, recibe "Sin
  acceso a Rodales". El servidor rechaza cada consulta de datos sin ese
  permiso, incluidos los polígonos del mapa.
- **Ser administrador de Transelec no da acceso a Rodales.** El primer
  administrador de Rodales se configura por su correo, una sola vez; desde
  ahí, él o ella da acceso a los demás. Cada cambio de acceso queda
  registrado.
- **Los datos se cargan de forma controlada.** Antes de que alguien pueda
  verlos, se verifica que la carga coincide exactamente con la base
  revisada: 1.568 polígonos, 10.422,61 ha, 7 geometrías inválidas, 1 cambio
  de clase y 72 cambios de código entre 2024 y 2026. Si algo no coincide,
  no se guarda nada.

## Mapa de fondo

Los polígonos y sus datos nunca salen de la plataforma. El mapa de fondo
(OpenStreetMap o imagen satelital de Esri) sí se descarga de esos
proveedores, que ven qué zona del mapa se está mirando. La opción "Sin
fondo" evita esas descargas.

## Qué necesitamos de Campo Digital

1. ¿Quién será el primer administrador de Rodales (correo)?
2. ¿Es aceptable usar el mapa de OpenStreetMap y la imagen satelital de Esri
   para ver el patrimonio? Si no, se deja solo "Sin fondo" u OpenStreetMap.

## Qué viene después

Cargar nuevas versiones del shapefile desde la plataforma, con revisión y
"Publicar": ver [Cargar, revisar y publicar versiones](carga-y-publicacion.md).

## Documentación relacionada

[Detalle técnico (inglés)](../hosted-release-v1.md) ·
[Visor V1](dashboard-v1.md) ·
[Preguntas para Campo Digital](preguntas-campo-digital.md)
