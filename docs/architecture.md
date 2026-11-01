# Arquitectura modular

## Decisión

Un monolito modular: una aplicación y una base PostgreSQL, con módulos de negocio separados. Mantener despliegue y operación simples para un desarrollador, un plazo de dos semanas y un presupuesto de hosting de USD 35 mensuales.

```text
backend/
  src/parrilladas/
    main.py                 # composición y ciclo de vida
    core/                   # configuración transversal
    db/                     # Base, sesiones y registro de modelos
    modules/
      accounts/             # cuentas, autenticación, Admin y Sales
      leads/                # contacto y datos del evento
      conversations/        # flujo guiado, historial y control humano
      quotes/               # precios manuales, versiones y aprobación
      reminders/            # tareas internas de seguimiento
      dashboard/            # composición de páginas Jinja2/HTMX
      health/               # probes públicos
    integrations/whatsapp/  # transporte Meta, firmas y errores externos
  migrations/               # historial de schema versionado
  tests/
```

## Reglas de dependencia

- `router.py`: HTTP, validación de entrada y respuesta; delega operaciones a servicios.
- `schemas.py`: contratos de entrada/salida de cada módulo, añadidos al implementar sus operaciones. No exponer modelos ORM directamente.
- `service.py`: casos de uso, autorización de negocio y transacciones explícitas. Los servicios se prueban con dependencias inyectadas.
- `repository.py`: consultas SQLAlchemy, añadido cuando existan consultas; recibe una sesión. Sin HTTP, commits ocultos ni reglas comerciales.
- `models.py`: tablas del módulo. Las relaciones entre módulos usan IDs y claves foráneas.
- `policies.py`: reglas puras cuando aportan claridad; no consulta DB ni llama proveedores.
- `main.py` compone routers e infraestructura; no acumula lógica de negocio.
- Un módulo accede a otro por servicios o contratos públicos. No importar routers o repositorios internos de otro módulo. `db/models.py` es la excepción explícita para registrar metadata de migraciones.
- `dashboard` compone datos de servicios y los presenta; no duplica reglas comerciales.
- `integrations` traduce protocolos externos, sin decidir precios, permisos o estados de venta.
- Evitar repositorios base, capas genéricas y herencias de servicios hasta que exista repetición real que lo justifique.

Se crean archivos conforme existe comportamiento que implementar; las carpetas no contienen servicios o repositorios vacíos para simular avance.

## Datos e integridad

- Identificadores UUID, timestamps con zona horaria, importes `Decimal`/`NUMERIC`, claves foráneas y nombres estables de constraints.
- Fecha del evento como fecha local. Timestamps operativos en UTC; presentación del negocio en `America/Costa_Rica`.
- La fecha/hora exacta del recordatorio del día siguiente se definirá al implementar tareas.
- `Quote.total = NULL` significa borrador sin precio. Nunca asumir un precio por defecto.
- Cada edición incrementará `version`. Solo podrá enviarse una versión que Daniel haya aprobado; enviar sigue siendo una acción explícita.
- El ID externo único del mensaje permite implementar idempotencia. La constraint es una base; aún falta implementar manejo de reintentos y duplicados.
- Cuentas referenciadas por historial no deben borrarse en cascada. Implementar desactivación para conservar trazabilidad.
- Modelos y migraciones son la base inicial, no sustituyen validación de schemas, permisos o transacciones.

## Seguridad y operación por implementar

Antes de exponer datos privados: sesiones seguras, contraseñas con hash resistente, CSRF para formularios y HTMX, roles comprobados en servidor, límites de intentos y bootstrap de administrador sin contraseña por defecto.

Antes de conectar Meta: validación de firma sobre el body original, verificación de webhook, persistencia idempotente antes de confirmar recepción, separación entre bot y atención humana, y reintentos persistentes. No usar tareas en memoria para envíos críticos. No registrar tokens ni contenido sensible por defecto.

El envío de cotización y la creación de recordatorio requieren una estrategia transaccional/outbox para recuperarse de fallos entre DB y Meta. La aprobación por sí sola no crea un envío. Un recordatorio interno nunca dispara un WhatsApp al cliente.

Uploads y PDFs permanecerán privados con acceso autorizado. La elección de almacenamiento, backups y hosting queda pendiente. Docker ejecuta la app como usuario sin privilegios; la configuración y los datos se mantienen fuera de la imagen.

## Referencias

- [FastAPI: aplicaciones divididas en módulos](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [FastAPI: ciclo de vida de recursos](https://fastapi.tiangolo.com/advanced/events/)
- [Alembic: entorno de migraciones](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
