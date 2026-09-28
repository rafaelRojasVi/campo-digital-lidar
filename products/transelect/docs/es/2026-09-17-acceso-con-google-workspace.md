# Transelec — inicio de sesión con Google Workspace (2026-09-17)

Documento de colaboración para Campo Digital y Javier. Explica cómo se
entrará al tablero de Transelec cuando esté en línea, qué debe configurar
Javier en Google Cloud, y qué falta todavía para poder decir que funciona.

La versión técnica completa está en
`docs/adr/ADR-010-google-workspace-sign-in-for-transelec.md` (inglés), y los
pasos exactos de la consola en
`docs/platform/google-workspace-oauth-handoff.md` (inglés).

## Qué cambió y por qué

Hasta ahora la plataforma iba a usar cuentas Microsoft. En septiembre quedó
establecido que **no existe un directorio Microsoft de Campo Digital**: la
carpeta compartida es un OneDrive personal, no una organización de Microsoft
365, y crear una exige un registro en Azure con verificación de tarjeta.

Campo Digital **sí** tiene Google Workspace en el dominio `campodigital.cl`.
Para el piloto de Transelec conviene más un proveedor de identidad que ya
existe que uno mejor en teoría y bloqueado en la práctica.

Entonces: **el tablero de Transelec se entrará con «Continuar con Google»**,
usando las cuentas `@campodigital.cl`. Microsoft sigue implementado y
disponible para los otros productos (LiDAR y Gestión Predial Forestal); no se
eliminó nada de ese lado.

## Cómo se ve para quien entra

1. La persona abre el tablero y ve un solo botón: **Continuar con Google**.
2. Google le pide elegir su cuenta `@campodigital.cl`.
3. Vuelve al tablero y ve lo que sus permisos le permiten ver.

No hay contraseña propia de Campo Digital que recordar, ni usuarios creados a
mano. Los botones de demostración («entrar como administrador», «ver como
Javier») **no existen** en la versión publicada: están eliminados del archivo
que se despliega, no solamente ocultos.

Si en algún entorno falta la configuración de Google, la pantalla lo dice con
claridad y se detiene. Nunca cae de vuelta a un acceso de demostración.

## Entrar no es tener permiso

Esto es importante y es deliberado:

> Una cuenta válida de `campodigital.cl` que no tenga permiso sobre Transelec
> inicia sesión correctamente y, aun así, **no ve el seguimiento**: el
> servidor le responde «no autorizado» (403).

Autenticarse responde *quién es usted*. Autorizar responde *qué puede hacer*,
y eso lo decide el permiso que tenga su cuenta sobre el producto Transelec.
Son dos pasos distintos y siguen siéndolo.

Tampoco basta con que el correo termine en `@campodigital.cl`: el servidor
exige que Google afirme, dentro del token firmado, que la cuenta pertenece al
Workspace de `campodigital.cl`. Una dirección que sólo *parece* del dominio no
entra.

## Cómo se reparten los permisos al principio

1. **El primer administrador.** Se configura una única dirección de correo
   que, al iniciar sesión por primera vez, recibe el rol de administrador
   **sólo sobre Transelec**. Nunca sobre LiDAR ni sobre Forestal. Es por una
   sola vez: si más adelante se le baja el rol, volver a entrar no se lo
   devuelve.
2. **El resto del equipo.** Los agrega ese administrador, por correo, desde la
   plataforma. Con una condición práctica: **cada persona debe haber iniciado
   sesión al menos una vez antes** de que se le pueda asignar un permiso,
   porque su cuenta en la plataforma recién existe desde ese momento.

   Es decir, el orden real es: la persona entra una vez (y verá un mensaje de
   «sin permisos»), y después el administrador le asigna el rol —
   `viewer` para consultar el tablero, `operator` o `admin` para además
   importar planillas y publicar o restaurar versiones.

   El formulario **Datos → Accesos** ofrece sólo `viewer` y `operator`, a
   propósito. Nombrar a un **segundo administrador** se hace con la misma
   API que usa ese formulario, que sí acepta `admin`.

### Actualización (2026-09-25): segundo administrador

1. La dirección de primer administrador sigue siendo la de **Javier**, hasta
   confirmar que su rol de administrador quedó creado: la sección
   **Datos → Accesos** se le abre y lo muestra como `admin`.
2. La cuenta Workspace de Rafael entra una vez (verá «sin permisos»).
3. Javier, con su sesión abierta en el tablero, le asigna `admin` a esa
   cuenta. Los pasos exactos, con el fragmento para la consola del
   navegador, están en `docs/platform/google-workspace-oauth-handoff.md`,
   sección «Handing administration to a second named account».
4. Javier conserva su propio rol.

Cada cambio de rol queda registrado en el historial de auditoría de la
plataforma: quién lo hizo, a quién, qué rol tenía antes y cuál tiene ahora.
El rol inicial de Javier queda registrado como otorgado por configuración.

## Qué debe configurar Javier

En la consola de Google Cloud, en un proyecto del dominio `campodigital.cl`.
El detalle exacto está en `docs/platform/google-workspace-oauth-handoff.md`;
el resumen:

1. **Pantalla de consentimiento OAuth** (o «Público» / *Audience*).
   Permisos solicitados: únicamente `openid`, `email` y `profile`. Nada más
   — esta aplicación no lee Drive, ni correo, ni calendario. Lo ideal es el
   tipo **Interno** (sólo cuentas `campodigital.cl`), pero sólo existe si el
   proyecto pertenece a la organización `campodigital.cl`. **Pregunta
   abierta:** qué tipo tiene realmente el cliente ya creado. Si es
   **Externo** y está «en pruebas», sólo pueden entrar los usuarios de
   prueba que figuren en esa página. En cualquier caso, el servidor exige
   por su cuenta que Google certifique la pertenencia al Workspace
   `campodigital.cl`.
2. **Cliente OAuth de tipo «Aplicación web».** Actualización (2026-09-25):
   ya está creado, y su **URI de retorno** registrada es

   `https://campo-digital-platform-production.up.railway.app/api/auth/google/callback`

   **Es correcta y no hay que cambiarla.** El `/api` debe estar: la
   plataforma arma la URI a partir de su configuración, que termina en
   `/api`, y Google exige que coincida carácter por carácter. Quitarlo en
   Google haría fallar todos los ingresos.
3. Entregar por un canal seguro (no correo ni chat en texto plano):
   - el **ID de cliente**;
   - el **secreto de cliente**.
4. Decidir **cuál dirección `@campodigital.cl`** será el primer administrador
   de Transelec.

## Qué falta para poder decir que funciona

**Todavía no se ha probado contra Google.** Todo lo implementado está
verificado con pruebas automáticas, incluidas pruebas criptográficas reales
con tokens firmados localmente (firma correcta e incorrecta, clave
desconocida, token vencido, dominio equivocado, correo no verificado, y más).
Pero ninguna de esas pruebas habla con Google.

Para confirmarlo hace falta, y aún no ocurre:

- confirmar el tipo de acceso del cliente (Interno o Externo);
- **una prueba real de inicio de sesión** con una cuenta `@campodigital.cl`,
  que es lo único que puede confirmar que el dominio llega como se espera y
  que el primer administrador recibe el rol correcto.

Hasta que esa prueba se haga, «el acceso con Google funciona» es una
expectativa bien fundamentada, no un hecho confirmado.

## Documentación relacionada

[Estado de los planes de manejo](2026-09-15-estado-planes-de-manejo.md) ·
[ADR-010 — Google Workspace sign-in (inglés)](../../../../docs/adr/ADR-010-google-workspace-sign-in-for-transelec.md) ·
[Pasos en Google Cloud (inglés)](../../../../docs/platform/google-workspace-oauth-handoff.md)
