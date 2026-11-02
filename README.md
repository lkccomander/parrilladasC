# Parrilladas

Agent for Budgets — repositorio `parrilladasC`.

Plataforma comercial de Parrillas en su Casa: WhatsApp guiado, atención humana desde un dashboard privado, cotizaciones revisadas por Daniel y recordatorios internos.

## Estado

Funcionan FastAPI, PostgreSQL, health checks, login/logout, permisos Admin/Sales y gestión de cuentas desde el dashboard. Las cuentas se desactivan para conservar el historial. Conversaciones reales, cotizaciones, PDF y recordatorios operativos son los próximos módulos. No conectar aún el webhook de producción.

Admin y API viven en servicios independientes: navegador → Admin → API con Bearer JWT → PostgreSQL. Admin no tiene acceso directo a la base ni a la clave de firma.

Stack confirmado: Python 3.12, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Jinja2 y HTMX. HTMX se incorporará cuando aporte interacción útil; las pantallas actuales funcionan sin JavaScript.

Panel privado: `/dashboard`. Crear el primer Admin con `parrilladas-admin bootstrap-admin` desde una terminal privada con el entorno y la base correctos. No hay contraseña predeterminada. Consultar [acceso y cuentas](docs/accounts.md).

El login y el panel comparten el diseño oscuro de las referencias acordadas, con fuentes locales. Páginas públicas: `/privacy` y `/terms-of-service`. Consultar [diseño y contenido legal](docs/interface.md) para referencias, licencias y datos comerciales pendientes de completar.

## Inicio con Docker

Desde la raíz, copiar `.env.example` a `.env` y ejecutar:

```sh
docker compose up --build
```

Compose inicia PostgreSQL, ejecuta las migraciones una vez y arranca Admin en http://localhost:8000 y API en http://localhost:8001. Cada proceso tiene `/health/live`; `/health/ready` comprueba PostgreSQL en el API y disponibilidad del API en Admin. Documentación en http://localhost:8001/docs únicamente en desarrollo y pruebas. Para bootstrap local: `docker compose exec api parrilladas-admin bootstrap-admin`. Para detener: `docker compose down`; los datos permanecen en el volumen.

Los valores de `.env.example` son exclusivamente locales. Elegir contraseñas propias; si contienen caracteres reservados, codificarlos al construir una URL de conexión. El compose local presupone credenciales sencillas sin caracteres reservados para su URL interna.

## Desarrollo sin contenedor de aplicación

Desde la raíz (Python 3.12 o posterior):

```sh
python -m venv .venv
```

Activar con `source .venv/bin/activate` en Linux/WSL, o `.venv\Scripts\Activate.ps1` en PowerShell. Después:

```sh
python -m pip install -r backend/requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e backend
docker compose up -d db
```

Exportar `DATABASE_URL`, `JWT_SECRET` (mínimo 32 caracteres) y `API_BASE_URL` desde el entorno, o copiar `.env.example` a `backend/.env` para los comandos ejecutados dentro de `backend`:

```sh
cd backend
alembic upgrade head
uvicorn parrilladas.main:create_app --factory --reload --port 8001
# En otra terminal, desde backend (Admin no necesita DATABASE_URL ni JWT_SECRET):
uvicorn parrilladas.admin:create_app --factory --reload --port 8000
```

`.env` no se carga implícitamente desde carpetas superiores: la configuración lee el archivo del directorio actual. No ejecutar migraciones automáticamente dentro de los procesos web; producción necesita una fase de migración separada.

## Verificación

Desde la raíz con el entorno virtual activo:

```sh
ruff check backend
ruff format --check backend
pytest backend/tests
python -m pip check
```

Las pruebas de PostgreSQL requieren `TEST_DATABASE_URL` apuntando a una base vacía y desechable. La prueba de migraciones crea y revierte las tablas y rechaza una base que ya tenga tablas. Nunca usar una base de negocio para estas pruebas. CI proporciona su propia base efímera y ejecuta esta verificación.

`backend/requirements.lock` fija dependencias de ejecución y construcción; `requirements-dev.lock` añade herramientas de desarrollo. Se resuelven para Python 3.12 con marcadores de plataforma, incluyendo Windows y Linux. Para actualizarlos, instalar `uv` en un entorno de herramientas y ejecutar desde la raíz:

```sh
uv pip compile backend/pyproject.toml backend/requirements-build.in --universal --python-version 3.12 --no-annotate -o backend/requirements.lock
uv pip compile backend/pyproject.toml backend/requirements-build.in --extra dev --constraint backend/requirements.lock --universal --python-version 3.12 --no-annotate -o backend/requirements-dev.lock
```

Revisar los cambios, reinstalar en un entorno limpio y ejecutar CI antes de publicar. Los comandos resuelven versiones nuevas dentro de los rangos de `pyproject.toml`; las instalaciones normales usan exclusivamente los locks.

## Organización y mantenimiento

Consultar [arquitectura](docs/architecture.md), [plan de implementación](docs/implementation-plan.md) y [decisiones del MVP](proyect_brain/TECH_STACK_MVP.md).

Configuración de despliegue e infraestructura: [Railway](docs/railway.md).

## Git y GitHub

Repositorio: [lkccomander/parrilladasC](https://github.com/lkccomander/parrilladasC), rama `main`. Se conserva el commit inicial y la licencia MIT del repositorio. Revisar los archivos elegidos y ejecutar los checks antes de cada commit. Los archivos locales con credenciales, `.env`, `.gitnexus`, previews, uploads y documentos comerciales originales DOCX/PDF están excluidos.

Con `origin` configurado al repositorio y después de crear el commit:

```sh
git push -u origin main
```

El push requiere un commit previo y acceso al repositorio. No incluir credenciales ni datos de clientes en commits, logs, fixtures o capturas.
