# Arquitectura modular

## Decisión

Dos servicios desplegables independientes en el mismo repositorio, con una sola base PostgreSQL. El API conserva un backend modular; Admin renderiza Jinja2/HTMX y consume el API por HTTP. Esta decisión sustituye el despliegue combinado inicial por indicación del usuario.

```text
Navegador → Admin (web, HTTPS) → API (red privada, Bearer JWT) → PostgreSQL
```

Solo el API recibe `DATABASE_URL` y `JWT_SECRET`. Admin recibe `API_BASE_URL`; no abre conexiones SQL ni firma tokens. Ambos usan la misma imagen con distintos `APP_MODULE`. Presupuesto objetivo: USD 35 mensuales, sujeto al consumo de tres servicios.

```text
backend/
  src/parrilladas/
    main.py                 # composición y ciclo de vida del API
    admin.py                # composición del servicio Admin
    core/                   # configuración transversal
    db/                     # Base, sesiones y registro de modelos
    modules/
      accounts/             # cuentas, autenticación, Admin y Sales
      leads/                # contacto y datos del evento
      conversations/        # flujo guiado, historial y control humano
      assistant/            # extracción validada, confirmación y preferencias de modo
      quotes/               # precios manuales, versiones y aprobación
      reminders/            # tareas internas de seguimiento
      dashboard/            # composición de páginas Jinja2/HTMX
      health/               # probes públicos
    integrations/whatsapp/  # transporte Meta, firmas y errores externos
    integrations/vertex_ai/ # modelos con ADC o cuenta de servicio, sin reglas comerciales
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
- `dashboard` llama al API mediante `AdminApiClient` y presenta contratos; no importa servicios, repositorios ni modelos ORM de negocio. No duplica reglas comerciales.
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

## Seguridad y operación

El módulo accounts implementa JWT de acceso de 15 minutos, refresh tokens opacos rotativos con sesión persistente, Argon2id, CSRF para formularios y futuros clientes HTMX, roles comprobados en servidor, límites de intentos y bootstrap de administrador sin contraseña por defecto. Detalles y operación: [acceso y cuentas](accounts.md).

Antes de conectar Meta: validación de firma sobre el body original, verificación de webhook, persistencia idempotente antes de confirmar recepción, separación entre bot y atención humana, y reintentos persistentes. No usar tareas en memoria para envíos críticos. No registrar tokens ni contenido sensible por defecto.

El envío de cotización y la creación de recordatorio requieren una estrategia transaccional/outbox para recuperarse de fallos entre DB y Meta. La aprobación por sí sola no crea un envío. Un recordatorio interno nunca dispara un WhatsApp al cliente.

Uploads y PDFs permanecerán privados con acceso autorizado. Railway aloja Admin, API y PostgreSQL; almacenamiento de PDFs y verificación de backups siguen pendientes. Docker ejecuta la app como usuario sin privilegios; la configuración y los datos se mantienen fuera de la imagen.

## Referencias

- [FastAPI: aplicaciones divididas en módulos](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [FastAPI: ciclo de vida de recursos](https://fastapi.tiangolo.com/advanced/events/)
- [Alembic: entorno de migraciones](https://alembic.sqlalchemy.org/en/latest/tutorial.html)

## Interacciones y derivación

`conversations` conserva la identidad del contacto y el estado de atención actual.
`conversation_interactions` separa cada consulta, con código único, snapshot y
estado; un índice parcial permite una sola interacción activa por conversación.
Los mensajes nuevos se vinculan a su interacción, y el outbox de `messages` admite
un destinatario de asesor, propósito y dependencias de entrega. El servicio de
conversaciones decide derivación y reinicio; el adaptador Meta solo traduce mensajes
y plantillas. El worker existente entrega los trabajos persistidos y conserva
idempotencia. No se agrega otro servicio desplegable ni una cola en memoria.

El teléfono del asesor se edita en Admin → Asistente. Si no hay uno guardado,
se presenta el contacto predeterminado del negocio; un contacto personalizado
tiene prioridad. Este valor inicial no habilita las notificaciones ni modifica
la preferencia de lenguaje natural.


## Listado de interacciones en Admin

Atención y ventas consume `GET /conversations/interactions` mediante el cliente HTTP
con JWT. Admin y Sales pueden consultar; una sesión anónima no tiene acceso.
El servicio de consultas de conversaciones aplica la autorización y la transacción;
el repositorio realiza búsqueda, filtro por estado, conteo y paginación de 25 filas.
El contrato expone únicamente campos de presentación del snapshot y el contacto,
sin mensajes ni metadatos internos. La vista conserva las solicitudes independientes
de un mismo número y presenta fechas operativas en America/Costa_Rica.
El listado no altera estados, reinicia conversaciones ni envía mensajes.


## Conocimiento aprobado del asistente

`assistant.rag.KnowledgeService` publica versiones del catálogo y recupera fragmentos.
`rag_repository.py` posee SQL y `integrations/vertex_ai/knowledge.py` adapta embeddings
y selección de evidencia. La composición inyecta la fábrica de sesiones y el proveedor;
`conversations` solo llama a `AssistantService.answer_question`. El dashboard utiliza
`rag_contracts` y HTTP. La publicación manual termina todas las llamadas externas antes
de adquirir un bloqueo de publicación y abrir su transacción de escritura. Las lecturas
SQL son breves y cierran la transacción antes de consultar a Gemini. El catálogo empaquetado
sigue disponible como respaldo controlado.

## Telemetría del asistente

Los adaptadores Google envían observaciones numéricas al servicio público
`assistant.telemetry.Telemetry`. Este servicio valida un contrato cerrado y usa
`telemetry_repository` para escribir en una transacción independiente, sin claves
foráneas a conversaciones ni contenido del cliente. La composición conecta el
mismo colector a extracción, RAG y adaptadores; las cargas CLI también lo usan.
Un contexto de traza agrupa los pasos sin propagar identificadores de negocio.

Las decisiones internas y las invocaciones Google se cuentan por separado. Los
agregados se calculan en SQL con filtro del tenant activo, ventana temporal y
paginación acotada. El Admin recibe únicamente contratos HTTP y no abre conexiones
SQL. La telemetría es operativa y de mejor esfuerzo; no sustituye Cloud Billing.


## Área RAG y roles múltiples

El Admin agrupa conocimiento publicado y telemetría Gemini en la sección RAG,
exclusiva de Dev. Las rutas JSON correspondientes también exigen Dev y tienen
prefijo `/rag`; los alias anteriores conservan la misma autorización. Asistente
mantiene preferencias del modo y derivación comercial. Los servicios RAG siguen
en `modules/assistant`, junto a sus contratos y repositorios: el cambio organiza
la navegación y los permisos sin añadir un servicio desplegable.

`accounts.roles` permite varios roles por cuenta. Dev hereda Admin y añade RAG;
Admin sin Dev no accede al área técnica. Las dependencias HTTP y los servicios
usan la misma semántica de permisos. La migración `0009` conserva el acceso previo
sin otorgar Dev automáticamente. Las ediciones revocan las sesiones existentes.


La concesión de Dev exige además `DEV_ROLE_KEY`, un secreto del API en Railway.
`accounts.service` valida la llave antes de crear o modificar privilegios y protege
reactivación/cambios de credenciales de cuentas Dev. Admin solo transmite la entrada
transitoria por HTTP; no recibe el secreto de referencia. La ausencia de configuración
bloquea concesiones. No hay cambio de schema ni persistencia de la llave en PostgreSQL.
