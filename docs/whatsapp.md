# Recepción de WhatsApp

El API expone `GET /webhooks/whatsapp` para verificar la suscripción de Meta y
`POST /webhooks/whatsapp` para recibir eventos. Admin no expone estas rutas.
La recepción está deshabilitada (503) mientras no se configuren las cuatro
variables siguientes, exclusivamente en el servicio API:

| Variable | Uso |
|---|---|
| `WHATSAPP_APP_SECRET` | App Secret de la aplicación Meta; valida la firma HMAC SHA-256 |
| `WHATSAPP_VERIFY_TOKEN` | Token privado elegido por el operador para verificar la suscripción |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | ID de la cuenta de WhatsApp Business permitida |
| `WHATSAPP_PHONE_NUMBER_ID` | ID del número de Meta permitido, no el número telefónico |

Configurar solo parte de las variables impide iniciar el API. No se necesita un
token de envío para recibir eventos. `.env.example` incluye valores sintéticos
comentados; Compose pasa las variables opcionales únicamente al API.

## Panel de integraciones

Las cuentas Admin tienen acceso a **Integraciones** en `/dashboard/integrations`,
con un enlace desde Inicio y la navegación. Sales no puede ver la página ni
ejecutar diagnósticos, incluso llamando directamente al API.

Para mostrar la URL completa del webhook y realizar las comprobaciones, configurar
estas variables adicionales exclusivamente en el API:

| Variable | Uso |
|---|---|
| `API_PUBLIC_BASE_URL` | Origen público del API, por ejemplo `https://api.example.com`; HTTPS obligatorio en producción/staging |
| `WHATSAPP_ACCESS_TOKEN` | Token de Meta con acceso a la cuenta y permiso `whatsapp_business_management` |
| `WHATSAPP_GRAPH_API_VERSION` | Versión de Graph API habilitada para la aplicación, con formato `vNN.N` |

La URL visible se construye con el origen público y `/webhooks/whatsapp`. No se
infiere desde `API_BASE_URL`, que puede ser una dirección privada de Railway.
Si falta el origen público, la pantalla muestra la ruta y avisa que falta la URL.
Los tokens y secretos se muestran únicamente como configurados/pendientes;
sus valores nunca se devuelven al servicio Admin ni al navegador.

Abrir la página consulta configuración local. **Comprobar conexión** realiza un
GET a `https://graph.facebook.com/<versión>/<WABA_ID>/phone_numbers`, con
`fields=id`, `limit=100` y el token en la cabecera Bearer. Comprueba el acceso a la
cuenta y la presencia del ID del número configurado. Solo se consultan IDs;
no se envían mensajes ni se modifican suscripciones. Una lista parcial que no
incluye el número se muestra como sin confirmar. No se siguen redirecciones ni
URLs de paginación externas.

Los resultados incluyen fecha/hora de la comprobación en Costa Rica y mensajes
seguros para token/permisos, límites de consultas, fallos de red y respuestas
inválidas. No se guardan resultados ni se ejecutan comprobaciones automáticas.
La comprobación confirma acceso a la cuenta y al número; la verificación de
suscripción y entrega de eventos al webhook se valida por separado desde Meta.

El API ofrece `GET /integrations/whatsapp` y `POST /integrations/whatsapp/check`
con permisos Admin; el POST requiere CSRF. El formulario del dashboard también
valida CSRF antes de llamar al API. Estas funciones no necesitan migraciones
adicionales. Referencia del endpoint de consulta:
[SDK oficial de Meta](https://github.com/meta/facebook-python-business-sdk/blob/main/facebook_business/adobjects/whatsappbusinessaccount.py).

## Verificación y autenticación

Meta verifica la suscripción mediante `hub.mode=subscribe`, `hub.verify_token`
y `hub.challenge`. Solo un token correcto devuelve el desafío como texto plano.
Las respuestas no se almacenan en caché. El API elimina la query de la solicitud
antes de que Uvicorn registre el acceso; los proxies externos también deben omitir
las queries de esta ruta para no registrar el token de verificación.

Los POST requieren una única cabecera `X-Hub-Signature-256` con `sha256=<hex>`.
Se calcula HMAC con el App Secret sobre los bytes originales, antes de interpretar
JSON, y se compara en tiempo constante. La ruta recibe solicitudes de servidor a
servidor: usa esta firma, no cookies, JWT de usuario ni tokens CSRF. Los endpoints
del dashboard y las mutaciones de usuarios mantienen sus permisos y CSRF.

Las solicitudes sin firma válida reciben 401, el payload inválido 400, una cuenta
o número inesperado 403 y un body superior a 1 MiB 413, incluso si llega en chunks.
Los errores no incluyen tokens, SQL ni contenido del cliente.

## Persistencia y duplicados

Ejecutar `alembic upgrade head` antes de habilitar la recepción. La migración
`0003` crea `whatsapp_inbox_events`, registrada en la metadata de modelos.
Cada mensaje entrante, actualización de estado o notificación de error ocupa una
fila con su payload privado y la fecha UTC de recepción. `processed_at = NULL`
significa pendiente de procesamiento.

La identidad del mensaje combina cuenta, número e ID externo. La identidad de un
estado añade estado y timestamp del proveedor. El índice único y
`INSERT ... ON CONFLICT DO NOTHING` evitan duplicados entre reintentos, cambios de
agrupación y recepciones concurrentes. Las claves no dependen del texto del
mensaje ni del orden del JSON. Los estados distintos se conservan por separado.
Las notificaciones de error se deduplican con su contenido canónico.

Se valida todo el lote antes de escribir y se confirma en una sola transacción.
Solo después del commit se responde 200. Un fallo de almacenamiento devuelve 503
para permitir el reintento de Meta, sin confirmar parcialmente el lote. Las
escrituras siguen un orden de claves estable para evitar bloqueos cruzados entre
lotes concurrentes. Los cambios de suscripción distintos del campo `messages`
se ignoran; los mensajes multimedia se conservan sin descargar archivos.

## Alcance de esta entrega

El inbox conserva eventos para el siguiente procesador persistente; todavía no
crea leads, conversaciones ni respuestas del bot, ni actualiza el estado comercial
de mensajes enviados. No hay envíos al cliente ni tareas en memoria tras responder.
No conectar el webhook de producción antes de implementar ese procesador, probar
staging y definir retención y control de acceso de los payloads. La base y sus
backups contienen datos privados; no copiar eventos reales a fixtures o logs.

Las pruebas usan payloads sintéticos. Las pruebas de idempotencia, concurrencia,
rollback y migración requieren `TEST_DATABASE_URL` en PostgreSQL vacío y desechable.

Protocolo de verificación y firma: [documentación de Meta](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/).
