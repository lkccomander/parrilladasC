# Acceso y cuentas

El panel se sirve desde `/dashboard`, con login en `/login`. Admin administra cuentas; Sales puede entrar al panel comercial, sin acceso a las pantallas ni operaciones de cuentas. Los módulos comerciales posteriores deben reutilizar las dependencias de autenticación y el servicio de cuentas.

## Primer administrador

Primero ejecutar `alembic upgrade head`. Desde `backend`, con el entorno del proyecto activo y `DATABASE_URL` configurada:

```sh
parrilladas-admin bootstrap-admin
```

El comando solicita correo, nombre y contraseña con confirmación. La contraseña no se muestra ni se pasa por argumentos o variables de entorno. No hay registro público ni contraseña inicial. El bootstrap solo funciona cuando no existen cuentas y usa un bloqueo transaccional de PostgreSQL para impedir dos primeros administradores concurrentes.

En Railway abrir una sesión SSH interactiva del servicio `web` y ejecutar el mismo comando dentro del contenedor. La sesión necesita una llave SSH registrada en la cuenta Railway. No ejecutar el bootstrap contra la base de pruebas ni guardar las credenciales en Git, comentarios o capturas.

En PowerShell, desde la raíz del repositorio con el CLI local instalado y la llave registrada durante la configuración de Railway:

```powershell
node .railway/cli.cjs ssh --service web --identity-file "$env:USERPROFILE\.ssh\id_ed25519_github" -- parrilladas-admin bootstrap-admin
```

Si la llave está en otra ubicación, ajustar `--identity-file`. El comando solicita los datos dentro de la terminal; no introducir contraseñas en el chat.

## Gestión desde el panel

- Crear cuentas con correo único, nombre y rol Admin/Sales.
- Editar los datos y cambiar la contraseña de forma opcional.
- Desactivar/reactivar cuentas. No se borran: se conserva el historial comercial y sus claves foráneas.
- Cada edición revoca las sesiones de la cuenta afectada. Si se edita la cuenta propia, debe volver a ingresar.
- Un Admin no puede desactivar su propia cuenta ni quitarse el rol Admin. Otra cuenta Admin puede realizar esos cambios, conservando siempre un administrador activo mediante operaciones serializadas.

Para recuperar una contraseña desde una sesión privada del operador:

```sh
parrilladas-admin reset-password
```

Solicita correo y nueva contraseña; revoca las sesiones existentes. No hay recuperación pública por correo en esta etapa. La entrega de contraseñas iniciales al equipo debe realizarse por un canal privado.

## Sesiones y protección

Contraseñas de 15–128 caracteres, almacenadas con Argon2id (19 MiB, dos iteraciones, paralelismo uno). Se permiten frases con espacios. Nunca se devuelve ni registra una contraseña desde los formularios.

Sesiones opacas aleatorias de 256 bits. PostgreSQL guarda únicamente el SHA-256 del identificador. La sesión autenticada vence a las ocho horas, sin renovación automática; la sesión del formulario de login vence a los 15 minutos. El login rota el identificador y el token CSRF. Logout, desactivación y edición revocan el acceso en servidor. Los registros vencidos se limpian al crear una sesión anónima.

En producción/staging, la cookie `__Host-parrilladas` tiene `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/` y ningún Domain. En desarrollo se utiliza una cookie sin Secure para localhost HTTP. APP_ENV debe permanecer `production` en Railway.

Todos los formularios POST, incluido login y logout, validan un token CSRF ligado a la sesión. También se acepta el header `X-CSRF-Token` para futuros clientes HTMX. Las solicitudes declaradas cross-site se rechazan. Los cuerpos de formularios se limitan a 16 KiB y se rechazan campos duplicados.

Cinco fallos por correo normalizado bloquean nuevos intentos durante el resto de una ventana de 15 minutos. Los contadores persisten en PostgreSQL, sobreviven al reinicio y usan un hash del correo como clave. Los errores de cuenta inexistente, contraseña incorrecta y cuenta inactiva son iguales. Esta protección no sustituye los controles de tráfico de infraestructura ante ataques de volumen.

Las páginas usan `Cache-Control: no-store`, protección de framing y una política de contenido sin scripts externos. Los campos del usuario se escapan en HTML. El panel inicial no necesita JavaScript ni HTMX todavía.

## Verificación

Las pruebas de cuentas usan exclusivamente `TEST_DATABASE_URL` con PostgreSQL vacío y desechable; migran, prueban y revierten sus tablas. No apuntar esa variable a Railway ni a una base de negocio.

La migración `0002` agrega sesiones y contadores; no modifica ni elimina las cuentas o el historial comercial. En Railway se aplica antes del despliegue mediante `alembic upgrade head`.

Referencias: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [argon2-cffi](https://argon2-cffi.readthedocs.io/en/stable/howto.html).
