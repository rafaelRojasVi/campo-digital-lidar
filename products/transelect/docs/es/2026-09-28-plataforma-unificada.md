# Plataforma Campo Digital: un solo ingreso para todos los proyectos (28-09-2026)

Este cambio está preparado, pero aún no está publicado en Railway.

## Qué cambia para quienes usan el panel

- La dirección principal (`campo-digital-platform-production.up.railway.app`) abre ahora la **entrada de Campo Digital**. Ahí se ingresa una sola vez con la cuenta de Google de Campo Digital.
- Después de ingresar se muestran los proyectos a los que cada persona tiene acceso. Hoy está Transelec. Rodales aparece como «Próximamente» para quien tenga acceso.
- Transelec funciona igual que antes y ahora vive en `/transelec/`. Los enlaces guardados a páginas de Transelec siguen funcionando: si la sesión no está iniciada, llevan primero a la entrada.
- Dentro de Transelec, el botón **Proyectos** (arriba a la derecha) vuelve a la entrada. «Cerrar sesión» está en la entrada.
- En pantallas de notebook, la barra superior de Transelec ya no se superpone: la fecha de la versión activa se muestra sin la hora (la hora aparece al pasar el mouse) y, bajo 1.280 píxeles de ancho, las secciones se agrupan en el menú «Secciones».

## Qué no cambia

- Los permisos siguen decidiéndose en el servidor, proyecto por proyecto. Ocultar una tarjeta no quita ni da acceso.
- No cambian los datos ni las reglas de Transelec.

## Próximos pasos

1. Pantalla «Accesos» en la entrada, para asignar quién ve cada proyecto.
2. Publicar Rodales con sus datos protegidos por el ingreso y con la carga del shapefile (revisar y luego publicar).

Detalle técnico: [diseño de la plataforma unificada](../../../../docs/superpowers/specs/2026-09-28-unified-platform-design.md).
