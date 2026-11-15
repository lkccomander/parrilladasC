# Railway

La aplicación se despliega desde la raíz del repositorio mediante el `Dockerfile`. `.railway/railway.ts` configura los servicios y las migraciones previas al despliegue, junto con el health check `/health/ready`. Railway no aplica `railway.json` a servicios nuevos; se utiliza Infrastructure as Code.

Proyecto: [parrilladasC](https://railway.com/project/832fef61-ac94-4c39-baf0-44cc2ffc7614). Entorno inicial: `production`. Repositorio de la aplicación: `lkccomander/parrilladasC`, rama `main`.

URL inicial: https://web-production-528a1.up.railway.app

## Aplicar cambios de infraestructura

Herramientas: Node.js, CLI y SDK de Railway fijados en `.railway/package-lock.json`. La versión local evita depender del CLI global del equipo.

```sh
npm ci --prefix .railway
npm run --prefix .railway plan
npm run --prefix .railway apply
```

Revisar el plan antes de aplicar: para cambios de despliegue no se esperan eliminaciones de servicios, variables o volúmenes. Las variables son `unmanaged`: IaC no lee ni escribe sus valores, que permanecen en Railway. Importar con `--variables=unmanaged`; no usar `--include-variables`.

Autodeploy está habilitado para `main` en `api` y `web`, con **Wait for CI** activado en ambos (`checkSuites: true`). Verificado directamente en Railway después de corregir los permisos de GitHub. El workflow `Checks` se ejecuta en cada push; Railway espera su resultado antes de desplegar. Los servicios pueden actualizarse en momentos distintos, por lo que los cambios de contratos y migraciones deben mantener compatibilidad durante el despliegue.

Los watch paths actuales son `/backend/**`, `/Dockerfile` y `/.dockerignore` en ambos servicios. Un push que solo cambie documentación o `.railway/` no provoca un despliegue de la aplicación. `APP_MODULE` sigue seleccionando qué factory ejecuta cada servicio.

La fuente y `checkSuites` se conservan en `.railway/railway.ts`. No se guardan tokens personales en GitHub. Como alternativa operativa, se puede desplegar explícitamente desde el último commit de GitHub:

```sh
node .railway/cli.cjs redeploy --service api --from-source --yes
# Esperar que API esté listo antes de actualizar Admin:
node .railway/cli.cjs redeploy --service web --from-source --yes
```

Los cambios en `.railway/` requieren plan y aplicación explícita; Railway no evalúa ese archivo durante cada build de la aplicación. Revisar diferencias con el estado actual, incluyendo cambios de región o serverless hechos en el dashboard. No guardar tokens personales en GitHub para automatizar esta operación.

## Servicios

- `web`: Admin público, factory `parrilladas.admin:create_app`, sin acceso a PostgreSQL. Conserva el dominio inicial y serverless.
- `api`: JSON API privado, factory `parrilladas.main:create_app`, una instancia inicial, 1 CPU y 512 MiB. Permanece activo para llamadas por red privada.
- `Postgres`: base con volumen persistente; solo API tiene la referencia de conexión. Se conserva región US East y configuración existente de la base.

Variables de `web` (Admin):

| Variable | Valor |
|---|---|
| `APP_ENV` | `production` |
| `APP_MODULE` | `parrilladas.admin:create_app` |
| `API_BASE_URL` | `http://api.railway.internal:8080` |
| `PORT` | `8080` |

Variables de `api`:

| Variable | Valor |
|---|---|
| `APP_ENV` | `production` |
| `APP_MODULE` | `parrilladas.main:create_app` |
| `PORT` | `8080` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `DATABASE_POOL_SIZE` | `3` |
| `JWT_SECRET` | Secreto aleatorio independiente, mínimo 32 caracteres |
| `API_PUBLIC_BASE_URL` | `https://api-production-3c20d.up.railway.app` |

`JWT_SECRET` solo pertenece al API. No publicar ni reutilizar el ejemplo local. La API valida HS256, issuer `parrilladas-auth` y audience `parrilladas-api`. Cambiar la clave invalida JWT existentes; para revocar también renovaciones, revocar sesiones por operación de cuentas.

El API tiene el dominio público `https://api-production-3c20d.up.railway.app`, dirigido al puerto 8080. La URL de callback de Meta es `https://api-production-3c20d.up.railway.app/webhooks/whatsapp`. Admin sigue llamando al API por red privada; no se necesita CORS. La recepción permanece deshabilitada hasta configurar los secretos e IDs de WhatsApp descritos en [webhook e integraciones](whatsapp.md).

Solo el API ejecuta `alembic upgrade head` antes del despliegue; Admin no ejecuta migraciones. Si falla la migración o readiness, la versión nueva no se considera lista. El Dockerfile selecciona la factory mediante `APP_MODULE`, conserva `PORT` y ejecuta como usuario sin privilegios.

## Conexión con Google Cloud

El proyecto del piloto es `parrilladas-ai-pilot`. El API utiliza la cuenta
`parrilladas-railway-api@parrilladas-ai-pilot.iam.gserviceaccount.com`, con los roles
`roles/aiplatform.user` y `roles/serviceusage.serviceUsageConsumer`.
No utiliza las credenciales ADC personales del desarrollador.

Variables exclusivas de `api`, entorno `production`:

| Variable | Valor |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | `parrilladas-ai-pilot` |
| `GOOGLE_CLOUD_LOCATION` | `global` |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Secreto JSON de la cuenta de servicio; nunca guardar en Git |
| `VERTEX_CONNECTION_ENABLED` | `true`, permite una comprobación sintética explícita |
| `NATURAL_LANGUAGE_ENABLED` | Gate del API; `true` para activar extracción con la preferencia Admin |
| `CONVERSATION_WORKER_ENABLED` | `true` para procesar el inbox/outbox persistido |
| `CONVERSATION_PROCESSING_START_AT` | Fecha/hora UTC de activación, conservada entre despliegues |
| `ASSISTANT_TIMEOUT_MS` | `15000` en el piloto activo |

El adaptador carga el secreto en memoria y valida tipo, proyecto y URL de tokens.
Admin no recibe estas variables. El SDK y el comando de comprobación están
incluidos en la imagen desplegada. Configurar variables no conecta por sí solo
la extracción con WhatsApp.

La credencial se carga por stdin del CLI, sin imprimirla ni pasarla como argumento.
Tras cargarla, usar **api → Variables → GOOGLE_SERVICE_ACCOUNT_JSON → Seal** en el
dashboard de Railway para impedir su lectura posterior por CLI/API. La carga por
CLI no la sella automáticamente. Para rotarla: crear una nueva clave de esa cuenta,
reemplazar la variable, aplicar el cambio, verificar la conexión y revocar la clave
anterior en Google Cloud. No revocar primero la clave que está en uso.

El presupuesto de Google Cloud tiene alertas de USD 15/mes; no es un límite de
consumo. La comprobación realiza una llamada sintética con salida limitada a 512
tokens y sin Search/Maps. La activación de IA en conversaciones requiere el trabajo
pendiente descrito en [el módulo de asistente](assistant.md).

Verificación del 15 de noviembre de 2026: llamada sintética desde el contenedor API
de Railway con esa cuenta y modelo, extracción JSON correcta y readiness de API y
Admin con HTTP 200. Se reaplicó la imagen estable existente, sin publicar el código
local pendiente. Como esa imagen todavía no incluye Google Gen AI, la prueba usó
un entorno temporal aislado con `google-genai==3.3.0`, eliminado al terminar.
El bot permaneció con `NATURAL_LANGUAGE_ENABLED=false`.

Despliegue posterior del dashboard, 15 de noviembre de 2026:

- API: `beb1f7b1-4fab-4ea0-a1d5-8c6ead2f9353`, migración `0005` aplicada.
- Admin: `5974d44e-2aaf-4475-981a-fecbfebbd7c0`, tarjetas **Modo guiado** y
  **Lenguaje natural**, más etiqueta con el modo efectivo.
- Ambos servicios saludables (HTTP 200), dashboard privado (redirección al login)
  y comprobación sintética de Gemini correcta con el SDK de la imagen.
- Subida directa de un paquete aislado con la aplicación probada (183 pruebas),
  sin publicar notas, credenciales ni otros archivos locales. Esa subida no generó
  un commit; la entrega versionada posterior usa GitHub Actions y autodeploy.

La entrega **Beta 1.01 (`1.0.0-beta.2`)** incorpora el asistente a Git y valida en
**Checks** la consistencia entre la versión del paquete y la aplicación, además
de las pruebas y el empaquetado. Los dos servicios esperan CI en `main`; comprobar
que ambos despliegues correspondan al mismo commit antes de dar la entrega por lista.

El primer intento se detuvo en predeploy por una conexión cerrada al despertar
PostgreSQL. Se comprobó readiness del API existente y se reintentó la misma imagen
con éxito. Si PostgreSQL está suspendido, comprobar que haya despertado antes
de reintentar una migración fallida por conectividad.

## Comprobación

La entrega **Beta 1.02 (`1.0.0-beta.3`)** conecta Gemini con solicitudes nuevas de
WhatsApp. Publicar el código por GitHub y esperar **Checks**; las variables de
activación del API deben aplicarse al nuevo despliegue, nunca a la versión Beta 1.01
que todavía restringía extracción a piloto local. El Admin debe guardar su
preferencia con su cuenta: la activación de infraestructura no suplanta ese actor.

Para volver al modo guiado, apagar la preferencia o el gate del modelo. Mantener
el worker y su fecha de activación para conservar la recuperación de mensajes.
Las conversaciones pausadas/cerradas no se reabren y los intentos de envío inciertos
requieren revisión antes de cualquier reintento. Detalles: [asistente](assistant.md).

- `/`: acceso público al panel.
- `/login`: formulario de acceso, sin registro público.
- `/dashboard`: panel privado; `/dashboard/accounts` requiere Admin.
- `/health/live`: proceso disponible.
- `/health/ready`: Admin comprueba API; API comprueba PostgreSQL.
- `/docs` y `/openapi.json`: deshabilitados en producción.

El panel incluye login, permisos y gestión de cuentas. Antes de ingresar, crear el primer Admin mediante el comando privado documentado en [acceso y cuentas](accounts.md). Envío de mensajes, cotizaciones, PDF y tareas se implementan posteriormente. Todavía no corresponde conectar el webhook real de WhatsApp.

## Costos y datos

Presupuesto objetivo del proyecto: USD 35 mensuales. Los cobros dependen del consumo; disponer de tres servicios no garantiza una cifra fija. Revisar consumo del proyecto y evitar réplicas o servicios adicionales innecesarios. No aplicar un límite global de workspace para este proyecto: el workspace puede alojar otras aplicaciones.

Un volumen persistente no sustituye backups. La configuración y restauración de backups deben verificarse antes de usar datos de clientes.

Referencias: [Infrastructure as Code](https://docs.railway.com/infrastructure-as-code), [PostgreSQL](https://docs.railway.com/databases/postgresql), [control de costos](https://docs.railway.com/pricing/cost-control).
