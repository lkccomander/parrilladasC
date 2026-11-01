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

Los pushes de código a `main` disparan el despliegue de `web`. Los cambios en `.railway/` requieren plan y aplicación explícita; Railway no evalúa ese archivo durante cada build de la aplicación. No guardar tokens personales en GitHub para automatizar esta operación.

## Servicios

- `web`: aplicación FastAPI y páginas Jinja2; una sola instancia inicial, con límite de 1 CPU y 512 MiB de memoria.
- `Postgres`: PostgreSQL con volumen persistente y conexión privada desde `web`.

Variables de `web`:

| Variable | Valor |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `DATABASE_POOL_SIZE` | `3` |

La configuración acepta URLs `postgres://`, `postgresql://` y `postgresql+psycopg://`, seleccionando siempre el driver psycopg instalado. No copiar credenciales al código o a este documento. Railway aporta `PORT`; el comando Docker lo utiliza y conserva 8000 como valor local.

Antes de cada despliegue, Railway ejecuta `alembic upgrade head`. Si falla la migración o el health check, el nuevo despliegue no se considera listo. Las migraciones deben ser compatibles con la versión anterior cuando el sistema tenga tráfico.

## Comprobación

- `/`: acceso público al panel.
- `/login`: formulario de acceso, sin registro público.
- `/dashboard`: panel privado; `/dashboard/accounts` requiere Admin.
- `/health/live`: proceso disponible.
- `/health/ready`: conectividad a PostgreSQL.
- `/docs` y `/openapi.json`: deshabilitados en producción.

El panel incluye login, permisos y gestión de cuentas. Antes de ingresar, crear el primer Admin mediante el comando privado documentado en [acceso y cuentas](accounts.md). Envío de mensajes, cotizaciones, PDF y tareas se implementan posteriormente. Todavía no corresponde conectar el webhook real de WhatsApp.

## Costos y datos

Presupuesto objetivo del proyecto: USD 35 mensuales. Los cobros dependen del consumo; disponer de dos servicios no garantiza una cifra fija. Revisar consumo del proyecto y evitar réplicas o servicios adicionales innecesarios. No aplicar un límite global de workspace para este proyecto: el workspace puede alojar otras aplicaciones.

Un volumen persistente no sustituye backups. La configuración y restauración de backups deben verificarse antes de usar datos de clientes.

Referencias: [Infrastructure as Code](https://docs.railway.com/infrastructure-as-code), [PostgreSQL](https://docs.railway.com/databases/postgresql), [control de costos](https://docs.railway.com/pricing/cost-control).
