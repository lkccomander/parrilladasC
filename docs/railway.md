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

El flujo objetivo es push a `main` → GitHub Actions → despliegue automático de `api` y `web`. La fuente GitHub está conectada, pero Railway todavía rechaza crear el trigger automático porque no reconoce a un miembro del proyecto con acceso al repositorio. El propietario debe conectar GitHub en Railway y conceder acceso a `lkccomander/parrilladasC`; después habilitar autodeploy para `main`, con Wait for CI.

Mientras se completa esa conexión, desplegar explícitamente desde el último commit de GitHub (no sube archivos locales):

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

`JWT_SECRET` solo pertenece al API. No publicar ni reutilizar el ejemplo local. La API valida HS256, issuer `parrilladas-auth` y audience `parrilladas-api`. Cambiar la clave invalida JWT existentes; para revocar también renovaciones, revocar sesiones por operación de cuentas.

El API no tiene dominio público inicial. Admin hace llamadas desde el servidor por red privada; no se necesita CORS. Antes de conectar Meta se debe añadir una entrada pública al API con verificación de firma.

Solo el API ejecuta `alembic upgrade head` antes del despliegue; Admin no ejecuta migraciones. Si falla la migración o readiness, la versión nueva no se considera lista. El Dockerfile selecciona la factory mediante `APP_MODULE`, conserva `PORT` y ejecuta como usuario sin privilegios.

## Comprobación

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
