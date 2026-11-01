# Railway

La aplicación se despliega desde la raíz del repositorio mediante el `Dockerfile`. `railway.json` configura migraciones previas al despliegue y el health check `/health/ready`.

Proyecto: [parrilladasC](https://railway.com/project/832fef61-ac94-4c39-baf0-44cc2ffc7614). Entorno inicial: `production`. Repositorio de la aplicación: `lkccomander/parrilladasC`, rama `main`.

## Servicios

- `web`: aplicación FastAPI y páginas Jinja2; una sola instancia inicial.
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

- `/`: página de preparación pública.
- `/health/live`: proceso disponible.
- `/health/ready`: conectividad a PostgreSQL.
- `/docs` y `/openapi.json`: deshabilitados en producción.

Este primer despliegue establece infraestructura. El login, dashboard comercial, envío de mensajes, PDF y tareas se implementan posteriormente. Todavía no corresponde conectar el webhook real de WhatsApp.

## Costos y datos

Presupuesto objetivo del proyecto: USD 35 mensuales. Los cobros dependen del consumo; disponer de dos servicios no garantiza una cifra fija. Revisar consumo del proyecto y evitar réplicas o servicios adicionales innecesarios. No aplicar un límite global de workspace para este proyecto: el workspace puede alojar otras aplicaciones.

Un volumen persistente no sustituye backups. La configuración y restauración de backups deben verificarse antes de usar datos de clientes.

Referencias: [configuración como código](https://docs.railway.com/config-as-code/reference), [PostgreSQL](https://docs.railway.com/databases/postgresql), [control de costos](https://docs.railway.com/pricing/cost-control).
