# Transelec — alternativas de alojamiento del piloto (2026-09-16)

Documento de colaboración para Campo Digital y Javier. Acompaña a la página
`/transelec/alojamiento` del tablero, que muestra esta misma comparación con
los enlaces oficiales de cada servicio.

## Para qué existe esta página

Javier preguntó cuánto costaría tener el tablero en línea. La respuesta
involucra cuatro alternativas distintas, cada una compuesta por varios
servicios contratados por separado, así que en lugar de una tabla en un correo
la comparación vive en el propio tablero: una página a la que se llega por
enlace, con el enlace oficial de cada servicio para poder verificar los
precios.

La página **no** está en la barra de secciones. Las cinco secciones del tablero
responden preguntas sobre la planilla; el costo de infraestructura no es una de
ellas. Se accede con la dirección directa, habiendo iniciado sesión.

## Alternativas comparadas

Ordenadas de menor a mayor costo mensual estimado, igual que en la página.

| Alternativa | Estimación mensual | Cómo se compone |
|---|---:|---|
| Render + almacenamiento de archivos | US$20–40 | Servicio web (US$7) + PostgreSQL administrado de 1 GB (US$19) + disco adicional (US$0,30 por GB). |
| Supabase + alojamiento de la aplicación | US$32–40 | Plan Pro (US$25, con 8 GB de base de datos, 100 GB de archivos y respaldos diarios) + alojamiento de la aplicación en Render o Fly.io (US$7 a US$8). |
| Fly.io | US$45–55 | Servidor de 1 GB (US$7,78) + Managed Postgres Basic con respaldos y alta disponibilidad (US$38) + 10 GB de disco (US$2,80). |
| Azure | desde US$45–55 | No compuesta servicio por servicio: se cotiza según la configuración elegida. |

Precios de lista de Fly.io, Render y Supabase consultados en sus páginas
oficiales el 2026-09-16. La cifra de Azure es un orden de magnitud pendiente de
cotización.

Observación para la conversación con Javier: **la alternativa más económica con
servicio administrado es Render**. Fly.io es la que proponemos evaluar primero
por simplicidad de operación, pero con base de datos administrada cuesta
aproximadamente lo mismo que Azure; con una base de datos autoadministrada en
el mismo servidor baja a unos US$15 al mes, sin respaldos ni alta
disponibilidad administrados, lo que no recomendamos para datos de Transelec.

## Qué tan firmes son estas cifras

**Son estimaciones preliminares de infraestructura, no una cotización.** Cada
cifra es una suma de precios de lista publicados por el propio proveedor,
consultados el 2026-09-16, sobre un dimensionamiento supuesto: un servidor de
aplicación pequeño, una base de datos administrada pequeña y unos pocos GB de
archivos. Ese dimensionamiento **no** está validado contra uso real, y las
cifras excluyen impuestos y tráfico fuera de lo previsto.

No provienen de la evidencia de precios de este repositorio: el estudio de
proveedores (`docs/research/2026-09-01-platform-runtime-infrastructure-study.md`,
con precios verificados de Azure al 2026-09-01) y la línea base de costos
(`docs/platform/environments-and-costs.md`, snapshot 2026-08-27) están
orientados a GCP y Azure para la plataforma completa, no al piloto de Transelec
sobre Fly.io, Render o Supabase.

Por eso:

- ninguna cifra se presenta sin decir que está sujeta a plan, consumo y
  cotización;
- cada cifra dice de qué servicios está compuesta, para poder discutirla
  servicio por servicio;
- cada servicio enlaza a su página oficial de precios, y la página indica la
  fecha de revisión;
- las cifras deben re-verificarse antes de contratar cualquier servicio.

No incluyen dominio, impuestos, licencias de Microsoft 365 / OneDrive, ni horas
de desarrollo y soporte.

## Lo que sí está respaldado por evidencia del proyecto

- **Render** ya aloja hoy el entorno de pruebas del portal con datos
  sintéticos (`docs/adr/ADR-005-render-staging-experiment.md`,
  `docs/adr/ADR-007-hosted-product-composition-v1.md`).
- **Supabase** no ejecuta por sí solo procesos largos —sus Edge Functions se
  cortan a los 400 segundos—, por lo que la aplicación necesita igualmente
  otro servicio; su región más cercana es São Paulo, no Chile
  (`docs/research/2026-09-01-platform-runtime-infrastructure-study.md`).
- **Azure** tiene región Chile Central y es la única alternativa que se integra
  directamente con las cuentas Microsoft existentes
  (`docs/adr/ADR-004-revisit-production-cloud-provider-choice.md`).

## Preguntas abiertas

- Dimensionamiento real del piloto (memoria de la aplicación, tamaño de la base
  de datos, volumen de planillas guardadas), que es lo que convierte estas
  sumas de precios de lista en una cifra confiable.
- Cotización concreta de Azure, la única alternativa que no se puede componer
  desde una página de precios pública.
- Cuál de las alternativas prefiere Transelec antes de contratar.

## Documentación relacionada

[Estado de los planes de manejo](2026-09-15-estado-planes-de-manejo.md) ·
[Rediseño de la interfaz](2026-09-13-rediseno-interfaz-transelec.md) ·
[Empaquetado y despliegue (inglés)](../deployment.md)
