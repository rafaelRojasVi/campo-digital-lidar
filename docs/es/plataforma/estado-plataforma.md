# Estado actual de la plataforma Campo Digital

## Estado

Propuesta de fundación técnica — agosto de 2026.

## Resumen

Campo Digital ya cuenta con un monorepo que separa tres productos:

- LiDAR / Cubicación;
- Gestión Predial Forestal / QGIS;
- Transelec.

LiDAR es actualmente el producto técnicamente más maduro.

Forestal y Transelec todavía requieren convertir sus fuentes actuales
(Shapefile, Excel, dashboards y archivos de trabajo) en modelos, historial y
procesos reproducibles.

## Qué estamos construyendo

El objetivo es una plataforma única de empresa con:

- acceso controlado;
- navegación entre productos;
- dashboards por producto;
- historial de fuentes y cambios;
- PostgreSQL/PostGIS como base estructurada y geoespacial;
- almacenamiento separado para archivos grandes;
- ingesta controlada desde OneDrive;
- resultados y documentos generados;
- trazabilidad;
- respaldo y recuperación.

La plataforma no elimina las diferencias entre los tres productos.

Cada producto mantiene su propia lógica y su propio dashboard.

## Desarrollo local primero

Por ahora no es necesario contratar infraestructura productiva.

La arquitectura se construirá localmente con la misma forma conceptual que
tendrá producción:

```text
OneDrive sincronizado (solo lectura)
        |
        v
WSL / repositorio
        |
        +-- FastAPI
        +-- PostgreSQL/PostGIS local
        +-- almacenamiento local privado
        +-- procesamiento LiDAR
        +-- ingesta Forestal
        +-- ingesta Transelec
        +-- frontends
```

Costo incremental de infraestructura cloud durante esta etapa:

**USD 0/mes.**

Los costos existentes de Microsoft 365, GitHub, herramientas de IA u otros
servicios ya contratados no se incluyen en esa cifra.

## Producción futura

Cuando Campo Digital necesite acceso compartido real, la arquitectura local
podrá mapearse a infraestructura administrada.

Candidato actual:

```text
GCP Santiago
|
+-- Cloud Run             API
+-- Cloud SQL             PostgreSQL/PostGIS
+-- Cloud Storage         archivos y snapshots
+-- Cloud Run Jobs        procesamiento/ingesta
+-- Cloud Scheduler       programación
+-- Secret Manager        credenciales
```

La decisión final se revisará con precios y requisitos vigentes antes de
contratar producción.

## Presupuesto preliminar

Con el modelo de planificación revisado el 27-08-2026:

**objetivo inicial: USD 75–100/mes**

aproximadamente:

**CLP 69.000–92.000/mes**

usando 920,57 CLP/USD como referencia de planificación.

Esto no es una cotización contractual.

El principal costo fijo esperado será PostgreSQL administrado.

## Seguridad base

La plataforma debe cumplir desde el inicio con estas reglas:

- los usuarios no se conectan directamente a PostgreSQL;
- los archivos privados no son públicos por defecto;
- las credenciales no se guardan en Git;
- OneDrive se trata inicialmente como fuente de solo lectura;
- LOCAL, STAGING y PRODUCCIÓN no comparten secretos;
- cambios importantes deben poder quedar trazados;
- no se debe construir un sistema propio de contraseñas sin necesidad real.

El proveedor final de identidad y el modelo exacto de permisos todavía son
decisiones abiertas.

## Qué no debemos hacer

- convertir un computador personal en servidor de producción;
- usar OneDrive como base de datos;
- borrar archivos antiguos antes de inventariarlos;
- asumir que un archivo llamado `final` es necesariamente definitivo;
- guardar LAS/LAZ o archivos privados en Git;
- exponer PostgreSQL directamente a usuarios;
- mezclar la lógica de LiDAR, Forestal y Transelec;
- agregar infraestructura compleja sin una necesidad demostrable.

## Orden de trabajo

```text
Arquitectura y documentación
        |
        v
Fundación local PostgreSQL/PostGIS
        |
        v
Integración LiDAR
        |
        v
Contrato Forestal
        |
        v
Contrato Transelec
        |
        v
Portal y dashboards de empresa
        |
        v
Producción
```

## Próximo objetivo

Cerrar y validar la documentación de arquitectura actual.

Después, crear la fundación local:

1. PostgreSQL/PostGIS;
2. migraciones reproducibles;
3. snapshots/proveniencia;
4. almacenamiento de artefactos;
5. ejecución local de jobs;
6. integración de LiDAR como primer producto real sobre la fundación.

## Actualización — composición hospedada V1 (2026-09-01)

Desde la propuesta original de agosto, la plataforma ya avanzó más allá de
la fundación local: existe un despliegue de staging en Render (gratuito) con
el portal, la API compartida y PostgreSQL/PostGIS.

Lo nuevo en esta actualización:

- **LiDAR ya es accesible públicamente en staging**, sin ningún dato real de
  cliente — el estado hospedado muestra "sin mediciones" porque no se
  publica ningún archivo LAS/LAZ real ni ninguna copia del reporte local.
- **Forestal y Transelec todavía no están disponibles públicamente.** El
  portal lo indica honestamente (no se simula disponibilidad) porque
  publicarlos requeriría inventar datos sintéticos de negocio (Forestal) o
  una arquitectura que hoy solo está diseñada para acceso privado del
  cliente (Transelec).
- El portal ahora distingue explícitamente entre el entorno local y el
  entorno de staging, en vez de mostrar siempre lenguaje de "demo local" en
  una URL pública.
- El costo incremental sigue siendo **USD 0/mes**: no se agregó ninguna base
  de datos, almacenamiento ni servicio de backend nuevo — solo un sitio
  estático adicional gratuito para LiDAR.
- El inicio de sesión real (Entra ID) sigue bloqueado externamente; por eso
  la nueva página "Archivos" en staging muestra un mensaje honesto de que el
  inicio de sesión todavía no está disponible ahí, en vez de botones de
  desarrollo que no funcionarían.
